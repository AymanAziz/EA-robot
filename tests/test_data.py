"""Contract tests use fixed fixtures, never invented live market observations."""
from datetime import datetime, timezone

import httpx
import pandas as pd
import pytest

from papertrade.data import CoinbaseData, DataError, validate_candles


def candles(start="2025-01-01", periods=5):
    idx = pd.date_range(start, periods=periods, freq="15min", tz="UTC")
    return pd.DataFrame({"open": 100., "high": 102., "low": 99., "close": 101., "volume": 10.}, index=idx)


def test_incomplete_candle_is_not_available_to_decisions():
    frame = candles()
    result = validate_candles(frame, datetime(2025, 1, 1, 1, 5, tzinfo=timezone.utc), "crypto")
    assert len(result) == 4
    assert result.index[-1] == pd.Timestamp("2025-01-01T00:45:00Z")


@pytest.mark.parametrize("defect", ["duplicate", "gap", "negative", "range", "nan", "naive", "unsorted"])
def test_bad_market_history_fails_closed(defect):
    frame = candles()
    if defect == "duplicate":
        frame = pd.concat([frame, frame.iloc[-1:]])
    elif defect == "gap":
        frame = frame.drop(frame.index[2])
    elif defect == "negative":
        frame.loc[frame.index[1], "volume"] = -1
    elif defect == "range":
        frame.loc[frame.index[1], "high"] = 98
    elif defect == "nan":
        frame.loc[frame.index[1], "close"] = float("nan")
    elif defect == "naive":
        frame.index = frame.index.tz_localize(None)
    else:
        frame = frame.iloc[::-1]
    with pytest.raises(DataError):
        validate_candles(frame, datetime(2025, 1, 2, tzinfo=timezone.utc), "crypto")


def test_stale_data_rejected_when_freshness_requested():
    with pytest.raises(DataError, match="stale"):
        validate_candles(candles(), datetime(2025, 1, 2, tzinfo=timezone.utc), "crypto", require_fresh=True)


def test_coinbase_uses_documented_ohlcv_order_and_discards_outside_range():
    def handler(request):
        assert request.url.params["granularity"] == "900"
        return httpx.Response(200, json=[[1735689600, 99, 102, 100, 101, 10], [1735688700, 99, 102, 100, 101, 10]])
    adapter = CoinbaseData(httpx.Client(transport=httpx.MockTransport(handler)))
    frame = adapter.get_market_data("BTC/USD", datetime(2025, 1, 1, tzinfo=timezone.utc), datetime(2025, 1, 1, 0, 15, tzinfo=timezone.utc))
    assert frame.iloc[0].to_dict() == {"open": 100., "high": 102., "low": 99., "close": 101., "volume": 10.}
    assert len(frame) == 1


def test_provider_outage_is_not_a_synthetic_price():
    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(503)))
    with pytest.raises(DataError):
        CoinbaseData(client).get_market_data("BTC/USD", datetime(2025, 1, 1, tzinfo=timezone.utc), datetime(2025, 1, 2, tzinfo=timezone.utc))


def test_real_quote_contract_exposes_bid_ask_and_provider_timestamp():
    def handler(request):
        assert request.url.path == "/products/BTC-USD/ticker"
        return httpx.Response(200, json={"bid": "99000", "ask": "99001", "time": "2025-01-01T00:00:00Z"})
    quote = CoinbaseData(httpx.Client(transport=httpx.MockTransport(handler))).get_quote("BTC/USD")
    assert quote.bid == 99000
    assert quote.ask == 99001
    assert quote.timestamp == datetime(2025, 1, 1, tzinfo=timezone.utc)


def test_crossed_or_nonfinite_quote_rejected():
    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"bid": "99", "ask": "98", "time": "2025-01-01T00:00:00Z"})))
    with pytest.raises(DataError):
        CoinbaseData(client).get_quote("BTC/USD")


def test_market_calendar_includes_holidays_and_weekend_closures():
    from papertrade.calendars import is_market_open
    assert not is_market_open("equity", datetime(2025, 12, 25, 16, tzinfo=timezone.utc))
    assert is_market_open("equity", datetime(2025, 11, 3, 15, tzinfo=timezone.utc))
    assert not is_market_open("forex", datetime(2025, 11, 1, 15, tzinfo=timezone.utc))
    assert is_market_open("crypto", datetime(2025, 11, 1, 15, tzinfo=timezone.utc))
