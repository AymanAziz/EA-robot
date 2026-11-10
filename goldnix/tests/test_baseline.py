"""Behaviour tests for the random-entry drift baseline."""

from __future__ import annotations

import pandas as pd

from sim.baseline import eligible_signal_indices, run_random_baseline


def _config():
    return {
        "vol_ceiling_atr": 0.30,
        "stop_atr": 1.0,
        "target_atr": 2.0,
        "min_distance_usd": 0.50,
        "friday_no_entry_from_utc": "19:00",
        "friday_flat_utc": "20:00",
        "holiday_exclusion": True,
        "fill_policy": "stop_first",
        "gap_policy": "adverse_at_open_favourable_at_target",
    }


def _bars() -> pd.DataFrame:
    timestamps = pd.date_range("2025-01-06", periods=12, freq="h", tz="UTC")
    bid_open = [100.0 + index * 0.1 for index in range(12)]
    return pd.DataFrame(
        {
            "timestamp_utc": timestamps,
            "era": "D",
            "atr": 1.0,
            "bid_open": bid_open,
            "bid_high": [value + 0.4 for value in bid_open],
            "bid_low": [value - 0.4 for value in bid_open],
            "bid_close": [value + 0.1 for value in bid_open],
            "ask_open": [value + 0.2 for value in bid_open],
            "ask_high": [value + 0.6 for value in bid_open],
            "ask_low": [value - 0.2 for value in bid_open],
            "ask_close": [value + 0.3 for value in bid_open],
        }
    )


def test_random_baseline_is_reproducible_and_preserves_direction_counts():
    first = run_random_baseline(
        _bars(),
        _config(),
        longs=2,
        shorts=1,
        draws=4,
        seed=20261110,
    )
    second = run_random_baseline(
        _bars(),
        _config(),
        longs=2,
        shorts=1,
        draws=4,
        seed=20261110,
    )

    pd.testing.assert_frame_equal(first.trades, second.trades)
    counts = first.trades.groupby(["draw", "dir"]).size().unstack(fill_value=0)
    assert counts["BUY"].tolist() == [2, 2, 2, 2]
    assert counts["SELL"].tolist() == [1, 1, 1, 1]
    assert first.draws["baskets"].tolist() == [3, 3, 3, 3]


def test_eligible_pool_applies_vol_friday_and_holiday_filters():
    bars = _bars().iloc[:7].copy()
    bars["timestamp_utc"] = pd.to_datetime(
        [
            "2025-01-06T00:00:00Z",
            "2025-01-06T01:00:00Z",
            "2025-01-10T18:00:00Z",
            "2025-01-10T19:00:00Z",
            "2025-12-25T00:00:00Z",
            "2025-12-25T01:00:00Z",
            "2025-12-27T00:00:00Z",
        ],
        utc=True,
    )
    bars.loc[0, "ask_close"] = bars.loc[0, "bid_close"] + 0.31

    eligible = set(eligible_signal_indices(bars, _config()).tolist())

    assert 0 not in eligible  # signal-close spread exceeds 0.30 ATR
    assert 1 in eligible
    assert 2 not in eligible  # next bar is Friday at the no-entry cutoff
    assert 4 not in eligible  # signal bar is Christmas Day
