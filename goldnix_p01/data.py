"""Chronological executable quotes; absent observations are never interpolated."""

from pathlib import Path
import hashlib

import numpy as np
import pandas as pd

TICK_DTYPE = np.dtype([("utc_ms", "<i8"), ("bid", "<f8"), ("ask", "<f8")])


def validate_ticks(ticks):
    if len(ticks) == 0 or ticks.dtype != TICK_DTYPE:
        raise ValueError("Nonempty canonical tick array required")
    if (
        np.any(np.diff(ticks["utc_ms"]) < 0)
        or np.any(ticks["utc_ms"] < 0)
        or not np.isfinite(ticks["bid"]).all()
        or not np.isfinite(ticks["ask"]).all()
        or np.any(ticks["bid"] <= 0)
        or np.any(ticks["ask"] < ticks["bid"])
    ):
        raise ValueError("Invalid chronology or executable quote")
    spread = ticks["ask"] - ticks["bid"]
    return {
        "ticks": len(ticks),
        "first_utc_ms": int(ticks["utc_ms"][0]),
        "last_utc_ms": int(ticks["utc_ms"][-1]),
        "max_interquote_gap_ms": int(np.diff(ticks["utc_ms"]).max()) if len(ticks) > 1 else 0,
        "spread_quantiles": dict(
            zip(
                ("min", "p05", "median", "p95", "max"),
                map(float, np.quantile(spread, [0, 0.05, 0.5, 0.95, 1])),
            )
        ),
        "same_millisecond_pairs": int(np.sum(np.diff(ticks["utc_ms"]) == 0)),
    }


def read_ticks(path, *, server_offset=0):
    path = Path(path)
    if path.stat().st_size % TICK_DTYPE.itemsize:
        raise ValueError("Truncated quote archive")
    ticks = np.fromfile(path, dtype=TICK_DTYPE)
    ticks["utc_ms"] -= server_offset * 1000
    report = validate_ticks(ticks)
    report.update(sha256=hashlib.sha256(path.read_bytes()).hexdigest(), server_offset=server_offset)
    return ticks, report


def minute_bars(ticks):
    validate_ticks(ticks)
    frame = pd.DataFrame(ticks)
    frame["epoch_seconds"] = frame.utc_ms // 60000 * 60
    grouped = frame.groupby("epoch_seconds", sort=True)
    parts = []
    for side in ("bid", "ask"):
        parts.append(
            grouped[side]
            .agg(["first", "max", "min", "last"])
            .rename(
                columns={
                    "first": side + "_open",
                    "max": side + "_high",
                    "min": side + "_low",
                    "last": side + "_close",
                }
            )
        )
    result = pd.concat(parts, axis=1).reset_index()
    for kind in ("open", "high", "low", "close"):
        result["mid_" + kind] = (result["bid_" + kind] + result["ask_" + kind]) / 2
    result["timestamp_utc"] = pd.to_datetime(result.epoch_seconds, unit="s", utc=True)
    result["available_at"] = result.epoch_seconds + 60
    return result


def features(bars):
    """Strict previous-20 channel, simple ATR14 and the native 100-bar warmup."""
    result = bars.copy()
    previous_close = result.mid_close.shift(1)
    tr = pd.concat(
        [
            result.mid_high - result.mid_low,
            abs(result.mid_high - previous_close),
            abs(result.mid_low - previous_close),
        ],
        axis=1,
    ).max(axis=1)
    tr.iloc[0] = np.nan
    result["atr"] = tr.rolling(14, min_periods=14).mean()
    hi = result.mid_high.shift(1).rolling(20).max()
    lo = result.mid_low.shift(1).rolling(20).min()
    result["direction"] = np.select([result.mid_close > hi, result.mid_close < lo], [1, -1], 0)
    result.loc[result.index < 99, "direction"] = 0
    result["distance"] = np.maximum(2 * result.atr, 0.5)
    result["spread"] = result.ask_close - result.bid_close
    return result
