"""Behaviour tests for non-gated trade reporting metrics."""

import pandas as pd
import pytest

from metrics.report import (
    longest_losing_streak,
    reference_win_rates,
    time_in_market_share,
)


def test_longest_losing_streak_counts_consecutive_non_positive_results():
    assert longest_losing_streak([1.0, -1.0, -0.2, 0.5, -2.0]) == 2


def test_time_in_market_counts_inclusive_h1_bars_without_double_counting():
    bars = pd.DataFrame(
        {"timestamp_utc": pd.date_range("2025-01-01", periods=4, freq="h", tz="UTC")}
    )
    trades = pd.DataFrame(
        {
            "entry_ts": [bars.timestamp_utc.iloc[0], bars.timestamp_utc.iloc[3]],
            "exit_ts": [bars.timestamp_utc.iloc[1], bars.timestamp_utc.iloc[3]],
        }
    )

    assert time_in_market_share(trades, bars) == pytest.approx(0.75)


def test_reference_win_rates_use_actual_stop_and_spread():
    trades = pd.DataFrame({"atr": [1.0], "spread_paid": [0.3]})

    rates = reference_win_rates(trades, stop_atr=1.0, min_distance_usd=0.5)

    assert rates["mean_stop_usd"] == pytest.approx(1.0)
    assert rates["mean_spread_usd"] == pytest.approx(0.3)
    assert rates["break_even_win_rate"] == pytest.approx(1.3 / 3.0)
    assert rates["win_rate_for_plus_0_15r"] == pytest.approx(1.45 / 3.0)
