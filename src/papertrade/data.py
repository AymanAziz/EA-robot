"""Real historical data ingestion. No interpolation, generated prices, or silent provider fallback."""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

import httpx
import numpy as np
import pandas as pd

from papertrade.calendars import session_mask
from papertrade.domain import INSTRUMENTS, Broker, Quote

OHLCV = ["open", "high", "low", "close", "volume"]


class DataError(RuntimeError):
    pass


def validate_candles(frame: pd.DataFrame, now: datetime, market: str,
                     require_fresh: bool = False, max_age_seconds: int = 1200) -> pd.DataFrame:
    """Validate UTC candle OPEN timestamps; return only completed regular-session candles.

    Gaps are errors inside trading sessions. They are never forward-filled. Callers may
    explicitly collect a shorter contiguous period instead of changing observed history.
    """
    stamp = pd.Timestamp(now)
    if stamp.tzinfo is None or not isinstance(frame.index, pd.DatetimeIndex) or frame.index.tz is None:
        raise DataError("Timezone-aware UTC candle and current timestamps required")
    if frame.empty or not set(OHLCV).issubset(frame.columns):
        raise DataError("Empty or missing OHLCV data")
    if frame.index.has_duplicates or not frame.index.is_monotonic_increasing:
        raise DataError("Duplicate or unordered candle timestamps")
    data = frame.copy()
    data.index = data.index.tz_convert("UTC")
    if not (data.index == data.index.floor("15min")).all():
        raise DataError("Candle timestamps must be 15-minute opening boundaries")
    if (data.index > stamp + pd.Timedelta(seconds=5)).any():
        raise DataError("Future candle timestamp")
    if "complete" in data:
        if not data["complete"].isin([True, False]).all():
            raise DataError("Invalid candle completion flag")
        data = data[data["complete"] == True]  # noqa: E712 - accepts native bool and provider 0/1 only.
    data = data.loc[data.index + pd.Timedelta(minutes=15) <= stamp, OHLCV].astype(float)
    data = data.loc[session_mask(data.index, market)]
    if data.empty:
        raise DataError("No completed candles")
    if not np.isfinite(data.to_numpy()).all():
        raise DataError("Non-finite OHLCV values")
    if (data[["open", "high", "low", "close"]] <= 0).any().any() or (data.volume < 0).any():
        raise DataError("Nonpositive prices or negative volume")
    if ((data.high < data[["open", "close", "low"]].max(axis=1)) |
        (data.low > data[["open", "close", "high"]].min(axis=1))).any():
        raise DataError("Inconsistent OHLC price range")
    if len(data) > 1:
        expected = pd.date_range(data.index[0], data.index[-1], freq="15min")
        expected = expected[session_mask(expected, market).to_numpy()]
        if not expected.equals(data.index):
            raise DataError("Missing candle(s) inside a market session")
    if require_fresh and (stamp - data.index[-1]).total_seconds() > max_age_seconds:
        raise DataError("Market data is stale")
    return data


class CoinbaseData:
    """Coinbase Exchange public historical trades candles, maximum 300 buckets/request.

    This is Coinbase venue data. It must never be represented as an Alpaca quote.
    """
    def __init__(self, client: httpx.Client | None = None):
        self.client = client or httpx.Client(timeout=20, headers={"User-Agent": "papertrade/0.1"}, follow_redirects=False)

    def get_quote(self, symbol: str) -> Quote:
        if symbol not in ("BTC/USD", "ETH/USD"):
            raise DataError("Coinbase quote unavailable for this instrument")
        try:
            response = self.client.get(f"https://api.exchange.coinbase.com/products/{symbol.replace('/', '-')}/ticker")
            response.raise_for_status()
            payload = response.json()
            bid, ask = float(payload["bid"]), float(payload["ask"])
            stamp = pd.Timestamp(payload["time"])
            if stamp.tzinfo is None or not np.isfinite([bid, ask]).all() or bid <= 0 or ask < bid:
                raise ValueError("Invalid quote")
            return Quote(bid, ask, stamp.tz_convert("UTC").to_pydatetime())
        except (httpx.HTTPError, KeyError, ValueError, TypeError) as exc:
            raise DataError("Coinbase quote unavailable or invalid") from exc

    def get_market_data(self, symbol: str, start: datetime, end: datetime) -> pd.DataFrame:
        if symbol not in ("BTC/USD", "ETH/USD"):
            raise DataError("Coinbase public adapter supports BTC/USD and ETH/USD only")
        if start.tzinfo is None or end.tzinfo is None or end <= start:
            raise DataError("Invalid timezone-aware history interval")
        rows = []
        cursor = start
        while cursor < end:
            stop = min(cursor + timedelta(minutes=15 * 299), end)
            try:
                response = self.client.get(f"https://api.exchange.coinbase.com/products/{symbol.replace('/', '-')}/candles",
                                           params={"start": cursor.isoformat(), "end": stop.isoformat(), "granularity": 900})
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, list):
                    raise ValueError("Invalid candles payload")
                rows.extend(payload)
            except (httpx.HTTPError, ValueError, TypeError) as exc:
                raise DataError("Coinbase historical data unavailable or invalid") from exc
            cursor = stop
            if cursor < end:
                time.sleep(0.12)  # Stay below the public REST rate limit.
        if not rows:
            raise DataError("Provider returned no historical candles")
        try:
            frame = pd.DataFrame(rows, columns=["timestamp", "low", "high", "open", "close", "volume"])
            frame.index = pd.to_datetime(frame.pop("timestamp"), unit="s", utc=True)
            frame = frame.loc[~frame.index.duplicated(keep="last"), OHLCV].sort_index().astype(float)
            return frame.loc[(frame.index >= pd.Timestamp(start)) & (frame.index < pd.Timestamp(end))]
        except (ValueError, TypeError, KeyError) as exc:
            raise DataError("Invalid Coinbase candle schema") from exc


def collect_history(symbol: str, start: datetime, end: datetime, settings=None,
                    broker: Broker | None = None) -> pd.DataFrame:
    if symbol not in INSTRUMENTS:
        raise DataError("Unsupported symbol")
    instrument = INSTRUMENTS[symbol]
    if broker is not None:
        raw = broker.get_market_data(symbol, start, end)
    elif instrument.market == "crypto":
        raw = CoinbaseData().get_market_data(symbol, start, end)
    else:
        raise DataError("Equity/forex historical data requires configured paper-provider credentials")
    return validate_candles(raw, datetime.now(timezone.utc), instrument.market)
