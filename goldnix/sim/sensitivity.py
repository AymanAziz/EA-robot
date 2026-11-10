"""Predeclared, non-promotable sensitivity transforms."""

from __future__ import annotations

import pandas as pd


def scale_execution_spread(bars: pd.DataFrame, multiplier: float) -> pd.DataFrame:
    """Scale bid/ask distance while preserving signals, ATR, and bid bars."""
    scaled = bars.copy()
    for field in ("open", "high", "low", "close"):
        bid = scaled[f"bid_{field}"]
        spread = scaled[f"ask_{field}"] - bid
        scaled[f"ask_{field}"] = bid + spread * multiplier
    return scaled


def apply_vf_low_abs(bars: pd.DataFrame, *, window: int = 1000) -> pd.DataFrame:
    """Keep SELL signals only below 1.5x the strictly trailing volume median."""
    filtered = bars.copy()
    trailing_median = (
        filtered["provider_volume"].shift(1).rolling(window, min_periods=window).median()
    )
    keep_sell = filtered["provider_volume"] < 1.5 * trailing_median
    filtered.loc[filtered["signal"].eq(-1) & ~keep_sell, "signal"] = 0
    return filtered
