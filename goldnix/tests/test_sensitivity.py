"""Behaviour tests for one-change-at-a-time sensitivity transforms."""

import pandas as pd
import pytest

from sim.sensitivity import apply_vf_low_abs, scale_execution_spread


def test_spread_scaling_changes_only_ask_quotes_not_signal_or_atr():
    bars = pd.DataFrame(
        {
            "bid_open": [100.0],
            "bid_high": [101.0],
            "bid_low": [99.0],
            "bid_close": [100.5],
            "ask_open": [100.4],
            "ask_high": [101.5],
            "ask_low": [99.3],
            "ask_close": [100.7],
            "signal": [1],
            "atr": [2.0],
        }
    )

    scaled = scale_execution_spread(bars, 2.0)

    assert scaled.loc[0, "ask_open"] == pytest.approx(100.8)
    assert scaled.loc[0, "ask_high"] == pytest.approx(102.0)
    assert scaled.loc[0, "ask_low"] == pytest.approx(99.6)
    assert scaled.loc[0, "ask_close"] == pytest.approx(100.9)
    assert scaled.filter(like="bid_").equals(bars.filter(like="bid_"))
    assert scaled["signal"].tolist() == [1]
    assert scaled["atr"].tolist() == [2.0]


def test_vf_low_abs_uses_only_trailing_volume_and_filters_sells_strictly():
    bars = pd.DataFrame(
        {
            "provider_volume": [10.0, 10.0, 10.0, 14.9, 15.0, 100.0],
            "signal": [0, 0, 0, -1, -1, 1],
        }
    )

    filtered = apply_vf_low_abs(bars, window=3)

    assert filtered["signal"].tolist() == [0, 0, 0, -1, 0, 1]
