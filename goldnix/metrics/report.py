"""Non-gated descriptive metrics for the decision-config report."""

from __future__ import annotations

import numpy as np
import pandas as pd


def longest_losing_streak(r_multiples) -> int:
    """Return the longest consecutive run of negative basket results."""
    longest = 0
    current = 0
    for value in r_multiples:
        if value < 0:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return longest


def time_in_market_share(trades: pd.DataFrame, bars: pd.DataFrame) -> float:
    """Return the share of observed H1 bars occupied by at least one trade."""
    if bars.empty:
        raise ValueError("bars cannot be empty")
    timestamps = pd.DatetimeIndex(pd.to_datetime(bars["timestamp_utc"], utc=True))
    occupied = np.zeros(len(timestamps), dtype=bool)
    for trade in trades.itertuples():
        entry = pd.Timestamp(trade.entry_ts)
        exit_ = pd.Timestamp(trade.exit_ts)
        start = int(timestamps.searchsorted(entry, side="left"))
        end = int(timestamps.searchsorted(exit_, side="right"))
        occupied[start:end] = True
    return float(occupied.mean())


def reference_win_rates(
    trades: pd.DataFrame,
    *,
    stop_atr: float,
    min_distance_usd: float,
) -> dict[str, float]:
    """Compute spread-aware reference win rates from actual mean geometry."""
    stops = np.maximum(
        trades["atr"].to_numpy(dtype=float) * stop_atr,
        min_distance_usd,
    )
    mean_stop = float(stops.mean())
    mean_spread = float(trades["spread_paid"].mean())
    return {
        "mean_atr_usd": float(trades["atr"].mean()),
        "mean_stop_usd": mean_stop,
        "mean_spread_usd": mean_spread,
        "break_even_win_rate": (mean_stop + mean_spread) / (3 * mean_stop),
        "win_rate_for_plus_0_15r": (1.15 * mean_stop + mean_spread)
        / (3 * mean_stop),
    }
