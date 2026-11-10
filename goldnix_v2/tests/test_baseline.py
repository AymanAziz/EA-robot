"""Behaviour tests for the direction-aware V2 drift baseline."""

import pandas as pd

from goldnix_v2.baseline import run_v2_random_baseline


def test_baseline_draws_longs_and_shorts_only_from_matching_h4_regimes():
    timestamps = pd.date_range("2025-01-06", periods=20, freq="h", tz="UTC")
    bid_open = [100.0 + index * 0.1 for index in range(20)]
    bars = pd.DataFrame(
        {
            "timestamp_utc": timestamps,
            "atr": 1.0,
            "h4_oscillator": [25.0] * 9 + [-25.0] * 11,
            "bid_open": bid_open,
            "bid_high": [value + 0.4 for value in bid_open],
            "bid_low": [value - 0.4 for value in bid_open],
            "bid_close": [value + 0.1 for value in bid_open],
            "ask_open": [value + 0.2 for value in bid_open],
            "ask_high": [value + 0.6 for value in bid_open],
            "ask_low": [value - 0.2 for value in bid_open],
            "ask_close": [value + 0.2 for value in bid_open],
        }
    )
    config = {
        "vol_ceiling_atr": 0.15,
        "stop_atr": 1.0,
        "target_atr": 2.0,
        "min_distance_usd": 0.5,
        "friday_no_entry_from_utc": "19:00",
        "friday_flat_utc": "20:00",
        "holiday_exclusion": True,
        "fill_policy": "stop_first",
        "gap_policy": "adverse_at_open_favourable_at_target",
    }

    result = run_v2_random_baseline(
        bars,
        config,
        longs=2,
        shorts=2,
        draws=3,
        seed=7,
    )

    selected = result.trades.merge(
        bars["h4_oscillator"], left_on="signal_index", right_index=True
    )
    assert (selected.loc[selected["dir"] == "BUY", "h4_oscillator"] > 0).all()
    assert (selected.loc[selected["dir"] == "SELL", "h4_oscillator"] < 0).all()
    assert result.draws["baskets"].tolist() == [4, 4, 4]

