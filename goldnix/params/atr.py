"""ATR candidates evaluated against broker MT5 values."""

from __future__ import annotations

import numpy as np


def _prices(high, low, close) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    high = np.asarray(high, dtype=float)
    low = np.asarray(low, dtype=float)
    close = np.asarray(close, dtype=float)
    if high.ndim != 1 or low.ndim != 1 or close.ndim != 1:
        raise ValueError("high, low and close must be 1-D")
    if not (high.shape == low.shape == close.shape):
        raise ValueError("high, low and close lengths must match")
    return high, low, close


def true_range(high, low, close) -> np.ndarray:
    """Return true range, using high-low for the first available bar."""
    high, low, close = _prices(high, low, close)
    result = high - low
    if result.size > 1:
        previous_close = close[:-1]
        result[1:] = np.maximum.reduce(
            [
                high[1:] - low[1:],
                np.abs(high[1:] - previous_close),
                np.abs(low[1:] - previous_close),
            ]
        )
    return result


def atr_simple(high, low, close, period: int = 14) -> np.ndarray:
    """Return a simple moving average of true range."""
    ranges = true_range(high, low, close)
    result = np.full(ranges.size, np.nan)
    if ranges.size >= period:
        result[period - 1:] = np.convolve(ranges, np.ones(period) / period, mode="valid")
    return result


def atr_wilder(high, low, close, period: int = 14) -> np.ndarray:
    """Return Wilder-smoothed true range, seeded by the first period mean."""
    ranges = true_range(high, low, close)
    result = np.full(ranges.size, np.nan)
    if ranges.size < period:
        return result
    result[period - 1] = ranges[:period].mean()
    for index in range(period, ranges.size):
        result[index] = ((period - 1) * result[index - 1] + ranges[index]) / period
    return result
