"""Closed-bar Aroon oscillator crossing signals."""

from __future__ import annotations

import numpy as np

from signals.aroon import THRESHOLD

SELL = -1
NONE = 0
BUY = 1


def cross_series(oscillator, threshold: float = THRESHOLD) -> np.ndarray:
    """Return signals aligned to the closed bar on which each cross occurs."""
    oscillator = np.asarray(oscillator, dtype=float)
    if oscillator.ndim != 1:
        raise ValueError("oscillator must be 1-D")
    if threshold <= 0:
        raise ValueError("threshold must be greater than zero")
    signals = np.full(oscillator.shape, NONE, dtype=np.int8)
    if oscillator.size < 2:
        return signals

    previous = oscillator[:-1]
    current = oscillator[1:]
    valid = np.isfinite(previous) & np.isfinite(current)
    signals[1:][valid & (previous < threshold) & (current > threshold)] = BUY
    signals[1:][valid & (previous > -threshold) & (current < -threshold)] = SELL
    return signals
