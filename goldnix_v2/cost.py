"""Transaction-cost eligibility for the V2 research strategy."""

from __future__ import annotations

import numpy as np


def cost_eligible(close_spread, atr, *, max_spread_atr: float) -> np.ndarray:
    """Return which signal bars fit the predeclared spread-to-ATR budget."""
    spreads = np.asarray(close_spread, dtype=float)
    atr_values = np.asarray(atr, dtype=float)
    if spreads.ndim != 1 or atr_values.ndim != 1:
        raise ValueError("spread and ATR must be 1-D")
    if spreads.shape != atr_values.shape:
        raise ValueError("spread and ATR must have matching shapes")
    if max_spread_atr <= 0:
        raise ValueError("max_spread_atr must be positive")
    return (
        np.isfinite(spreads)
        & np.isfinite(atr_values)
        & (spreads > 0)
        & (atr_values > 0)
        & (spreads <= max_spread_atr * atr_values)
    )

