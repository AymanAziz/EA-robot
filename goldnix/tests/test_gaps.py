"""Behaviour tests for recorded market-data gaps."""

import pandas as pd
import pytest

from ingest.gaps import find_gaps


@pytest.mark.parametrize(
    ("start", "end", "expected_kind", "expected_hours"),
    [
        ("2024-01-08T00:00:00Z", "2024-01-08T05:00:00Z", "session", 5.0),
        ("2024-01-05T21:00:00Z", "2024-01-07T22:00:00Z", None, None),
        ("2024-01-05T21:00:00Z", "2024-01-08T10:00:00Z", "weekend", 61.0),
    ],
)
def test_gap_threshold_depends_on_whether_interval_crosses_weekend(
    start, end, expected_kind, expected_hours
):
    bars = pd.DataFrame({"timestamp_utc": pd.to_datetime([start, end])})

    gaps = find_gaps(bars)

    if expected_kind is None:
        assert gaps.empty
    else:
        assert gaps.iloc[0]["gap_kind"] == expected_kind
        assert gaps.iloc[0]["gap_hours"] == pytest.approx(expected_hours)
