"""Closed-H4 confirmation for H1 Aroon crossings."""

from __future__ import annotations

import numpy as np
import pandas as pd

from signals.aroon import aroon_osc_series
from goldnix_v2.cost import cost_eligible


def build_h4_oscillator(
    h1_bars: pd.DataFrame,
    *,
    period: int,
    ties: str,
    server_timezone: str,
) -> pd.DataFrame:
    """Aggregate H1 bars on broker-server H4 boundaries and calculate Aroon."""
    timestamps = pd.DatetimeIndex(
        pd.to_datetime(h1_bars["timestamp_utc"], utc=True, errors="raise")
    )
    if not timestamps.is_monotonic_increasing:
        raise ValueError("H1 timestamps must be sorted")
    server_times = timestamps.tz_convert(server_timezone).tz_localize(None)
    bucket_starts = server_times.normalize() + pd.to_timedelta(
        (server_times.hour // 4) * 4,
        unit="h",
    )
    mid = pd.DataFrame(
        {
            "high": (
                h1_bars["bid_high"].to_numpy(dtype=float)
                + h1_bars["ask_high"].to_numpy(dtype=float)
            )
            / 2,
            "low": (
                h1_bars["bid_low"].to_numpy(dtype=float)
                + h1_bars["ask_low"].to_numpy(dtype=float)
            )
            / 2,
            "bucket_start": bucket_starts,
        },
    )
    h4 = mid.groupby("bucket_start", sort=True).agg(
        high=("high", "max"),
        low=("low", "min"),
        bars=("high", "count"),
    )
    close_local = (h4.index + np.timedelta64(4, "h")).tz_localize(server_timezone)
    h4.index = close_local.tz_convert("UTC")
    h4["oscillator"] = aroon_osc_series(
        h4["high"].to_numpy(),
        h4["low"].to_numpy(),
        period=period,
        ties=ties,
    )
    return h4.rename_axis("close_time").reset_index()


def confirm_h1_crosses(
    h1_close_times,
    h1_crosses,
    h4_close_times,
    h4_oscillator,
) -> np.ndarray:
    """Keep an H1 cross only when the latest closed H4 trend agrees."""
    h1_times = pd.DatetimeIndex(pd.to_datetime(h1_close_times, utc=True))
    h4_times = pd.DatetimeIndex(pd.to_datetime(h4_close_times, utc=True))
    crosses = np.asarray(h1_crosses)
    oscillator = np.asarray(h4_oscillator, dtype=float)
    if crosses.ndim != 1 or oscillator.ndim != 1:
        raise ValueError("crosses and oscillator must be 1-D")
    if len(h1_times) != len(crosses) or len(h4_times) != len(oscillator):
        raise ValueError("timestamps and values must have matching lengths")
    if not h1_times.is_monotonic_increasing or not h4_times.is_monotonic_increasing:
        raise ValueError("timestamps must be sorted")

    latest = np.searchsorted(h4_times.asi8, h1_times.asi8, side="right") - 1
    confirmed = np.zeros(len(crosses), dtype=np.int8)
    available = latest >= 0
    h4_values = np.full(len(crosses), np.nan)
    h4_values[available] = oscillator[latest[available]]
    confirmed[(crosses == 1) & (h4_values > 0)] = 1
    confirmed[(crosses == -1) & (h4_values < 0)] = -1
    return confirmed


def apply_v2_confirmation(
    prepared_h1: pd.DataFrame,
    *,
    h4_period: int,
    ties: str,
    max_spread_atr: float,
    server_timezone: str,
) -> pd.DataFrame:
    """Apply the predeclared closed-H4 direction and cost gates."""
    prepared = prepared_h1.copy()
    h4 = build_h4_oscillator(
        prepared,
        period=h4_period,
        ties=ties,
        server_timezone=server_timezone,
    )
    h1_close_times = pd.DatetimeIndex(
        pd.to_datetime(prepared["timestamp_utc"], utc=True)
    ) + np.timedelta64(1, "h")
    h4_close_times = pd.DatetimeIndex(h4["close_time"])
    latest = np.searchsorted(
        h4_close_times.asi8,
        pd.DatetimeIndex(h1_close_times).asi8,
        side="right",
    ) - 1
    aligned_h4 = np.full(len(prepared), np.nan)
    available = latest >= 0
    aligned_h4[available] = h4["oscillator"].to_numpy()[latest[available]]

    raw_signal = prepared["signal"].to_numpy(dtype=np.int8)
    confirmed = confirm_h1_crosses(
        h1_close_times,
        raw_signal,
        h4["close_time"],
        h4["oscillator"],
    )
    eligible = cost_eligible(
        prepared["ask_close"].to_numpy() - prepared["bid_close"].to_numpy(),
        prepared["atr"].to_numpy(),
        max_spread_atr=max_spread_atr,
    )
    prepared["raw_signal"] = raw_signal
    prepared["h4_oscillator"] = aligned_h4
    prepared["cost_eligible"] = eligible
    prepared["signal"] = np.where(eligible, confirmed, 0).astype(np.int8)
    return prepared

