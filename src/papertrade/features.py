"""Causal features calculated at a completed candle's close. Never shift backwards."""
from __future__ import annotations

import numpy as np
import pandas as pd

FEATURE_VERSION = "causal-v1"


def build_features(candles: pd.DataFrame) -> pd.DataFrame:
    frame = candles
    close = frame.close.astype(float)
    ret = close.pct_change(fill_method=None)
    output = pd.DataFrame(index=frame.index)
    for bars in (1, 4, 16):
        output[f"return_{bars}"] = close.pct_change(bars, fill_method=None)
    output["sma20_gap"] = close / close.rolling(20).mean() - 1
    output["sma50_gap"] = close / close.rolling(50).mean() - 1
    ema12 = close.ewm(span=12, adjust=False, min_periods=12).mean()
    ema26 = close.ewm(span=26, adjust=False, min_periods=26).mean()
    output["macd"] = (ema12 - ema26) / close
    output["macd_signal"] = output.macd.ewm(span=9, adjust=False, min_periods=9).mean()
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    rsi = 100 - 100 / (1 + gain / loss.replace(0, np.nan))
    rsi = rsi.mask((loss == 0) & (gain > 0), 100)
    output["rsi14"] = rsi.mask((loss == 0) & (gain == 0), 50)
    tr = pd.concat([(frame.high - frame.low), (frame.high - close.shift()).abs(),
                    (frame.low - close.shift()).abs()], axis=1).max(axis=1)
    output["atr"] = tr.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    output["atr_pct"] = output.atr / close
    output["volatility"] = ret.rolling(20).std(ddof=1)
    output["momentum8"] = close.pct_change(8, fill_method=None)
    output["volume_change"] = frame.volume.pct_change(fill_method=None).replace([np.inf, -np.inf], np.nan).fillna(0)
    mean_volume = frame.volume.rolling(20).mean()
    output["volume_ratio"] = (frame.volume / mean_volume.replace(0, np.nan)).fillna(0)
    output["price_range"] = (frame.high - frame.low) / close
    output["trend_strength"] = (close.rolling(20).mean() - close.rolling(50).mean()) / output.atr.replace(0, np.nan)
    hours = frame.index.hour + frame.index.minute / 60
    output["hour_sin"] = np.sin(2 * np.pi * hours / 24)
    output["hour_cos"] = np.cos(2 * np.pi * hours / 24)
    output["weekday_sin"] = np.sin(2 * np.pi * frame.index.dayofweek / 7)
    output["weekday_cos"] = np.cos(2 * np.pi * frame.index.dayofweek / 7)
    london = frame.index.tz_convert("Europe/London")
    new_york = frame.index.tz_convert("America/New_York")
    output["london_session"] = ((london.hour >= 8) & (london.hour < 17)).astype(int)
    output["ny_session"] = ((new_york.hour >= 9) & (new_york.hour < 16)).astype(int)
    # Fixed volatility bands, not quantiles computed from future rows.
    output["regime"] = np.select([output.volatility > 0.015, output.trend_strength > 0.5,
                                   output.trend_strength < -0.5], [3, 1, 2], default=0)
    return output.replace([np.inf, -np.inf], np.nan).dropna()


def feature_regime(row: pd.Series) -> str:
    return {0: "range", 1: "uptrend", 2: "downtrend", 3: "high_volatility"}.get(int(row.regime), "unknown")
