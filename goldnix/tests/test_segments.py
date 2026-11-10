"""Behaviour tests for local volume-unit boundary detection."""

import pandas as pd
import pytest

from ingest.segments import find_volume_boundaries


def test_local_before_after_medians_find_the_center_of_a_sustained_unit_step():
    bars = pd.DataFrame(
        {
            "timestamp_utc": pd.date_range("2024-01-01", periods=40, freq="h", tz="UTC"),
            "provider_volume": [1.0] * 20 + [10.0] * 20,
        }
    )

    boundaries = find_volume_boundaries(bars, window=5, hold=3)

    assert len(boundaries) == 1
    boundary = boundaries.iloc[0]
    assert boundary["boundary_index"] == 20
    assert boundary["boundary_ts"] == pd.Timestamp("2024-01-01T20:00:00Z")
    assert boundary["before_median"] == pytest.approx(1.0)
    assert boundary["after_median"] == pytest.approx(10.0)
    assert boundary["ratio"] == pytest.approx(10.0)
    assert boundary["direction"] == "up"


def test_sustained_downward_unit_step_uses_the_less_than_point_two_rule():
    bars = pd.DataFrame(
        {
            "timestamp_utc": pd.date_range("2024-01-01", periods=40, freq="h", tz="UTC"),
            "provider_volume": [10.0] * 20 + [1.0] * 20,
        }
    )

    boundaries = find_volume_boundaries(bars, window=5, hold=3)

    assert boundaries.iloc[0]["boundary_index"] == 20
    assert boundaries.iloc[0]["ratio"] == pytest.approx(0.1)
    assert boundaries.iloc[0]["direction"] == "down"
