"""Behaviour tests for the predeclared V2 signal confirmation."""

import numpy as np
import pandas as pd

from goldnix_v2.signal import (
    apply_v2_confirmation,
    build_h4_oscillator,
    confirm_h1_crosses,
)


def test_h1_cross_uses_only_the_latest_fully_closed_h4_trend():
    h1_close_times = pd.to_datetime(
        [
            "2025-01-06T02:00:00Z",
            "2025-01-06T03:00:00Z",
            "2025-01-06T04:00:00Z",
            "2025-01-06T05:00:00Z",
        ],
        utc=True,
    )
    h1_crosses = np.array([-1, 1, -1, 1], dtype=np.int8)
    h4_close_times = pd.to_datetime(
        ["2025-01-06T00:00:00Z", "2025-01-06T04:00:00Z"],
        utc=True,
    )
    h4_oscillator = np.array([25.0, -25.0])

    confirmed = confirm_h1_crosses(
        h1_close_times,
        h1_crosses,
        h4_close_times,
        h4_oscillator,
    )

    assert confirmed.tolist() == [0, 1, -1, 0]


def test_h4_oscillator_is_timestamped_at_the_close_of_four_h1_bars():
    timestamps = pd.date_range("2025-01-06T00:00:00Z", periods=8, freq="h")
    mid_high = [9.0, 10.0, 9.5, 9.0, 10.0, 11.0, 12.0, 11.5]
    mid_low = [6.0, 5.0, 5.5, 6.0, 7.0, 6.5, 6.0, 6.5]
    bars = pd.DataFrame(
        {
            "timestamp_utc": timestamps,
            "bid_high": mid_high,
            "ask_high": mid_high,
            "bid_low": mid_low,
            "ask_low": mid_low,
        }
    )

    h4 = build_h4_oscillator(
        bars,
        period=2,
        ties="newest",
        server_timezone="UTC",
    )

    assert h4["close_time"].tolist() == [
        pd.Timestamp("2025-01-06T04:00:00Z"),
        pd.Timestamp("2025-01-06T08:00:00Z"),
    ]
    assert np.isnan(h4.loc[0, "oscillator"])
    assert h4.loc[1, "oscillator"] == 50.0


def test_v2_requires_both_h4_direction_and_cost_eligibility():
    timestamps = pd.date_range("2025-01-06T00:00:00Z", periods=9, freq="h")
    bars = pd.DataFrame(
        {
            "timestamp_utc": timestamps,
            "bid_high": [9, 10, 9.5, 9, 10, 11, 12, 11.5, 12],
            "ask_high": [9, 10, 9.5, 9, 10, 11, 12, 11.5, 12],
            "bid_low": [6, 5, 5.5, 6, 7, 6.5, 6, 6.5, 7],
            "ask_low": [6, 5, 5.5, 6, 7, 6.5, 6, 6.5, 7],
            "bid_close": [8.0] * 9,
            "ask_close": [8.1] * 8 + [8.2],
            "atr": [1.0] * 9,
            "signal": [0] * 7 + [1, 1],
        }
    )

    prepared = apply_v2_confirmation(
        bars,
        h4_period=2,
        ties="newest",
        max_spread_atr=0.15,
        server_timezone="UTC",
    )

    assert prepared["raw_signal"].tolist()[-2:] == [1, 1]
    assert prepared["h4_oscillator"].tolist()[-2:] == [50.0, 50.0]
    assert prepared["cost_eligible"].tolist()[-2:] == [True, False]
    assert prepared["signal"].tolist()[-2:] == [1, 0]


def test_h4_boundaries_follow_broker_server_time_in_winter():
    timestamps = pd.date_range("2025-01-05T22:00:00Z", periods=8, freq="h")
    bars = pd.DataFrame(
        {
            "timestamp_utc": timestamps,
            "bid_high": range(8),
            "ask_high": range(8),
            "bid_low": range(8),
            "ask_low": range(8),
        }
    )

    h4 = build_h4_oscillator(
        bars,
        period=2,
        ties="newest",
        server_timezone="Europe/Helsinki",
    )

    assert h4["close_time"].tolist() == [
        pd.Timestamp("2025-01-06T02:00:00Z"),
        pd.Timestamp("2025-01-06T06:00:00Z"),
    ]

