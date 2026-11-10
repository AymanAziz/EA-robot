"""Behaviour tests for declared UTC holiday exclusions."""

import pandas as pd
import pytest

from ingest.holidays import excluded_holiday


@pytest.mark.parametrize(
    ("timestamp", "expected"),
    [
        ("2024-12-24T12:00:00Z", "christmas_closure"),
        ("2024-12-25T12:00:00Z", "christmas_closure"),
        ("2024-12-26T12:00:00Z", "christmas_closure"),
        ("2025-01-01T12:00:00Z", "new_years_day"),
        ("2024-03-29T12:00:00Z", "good_friday"),
        ("2024-11-28T12:00:00Z", "us_thanksgiving"),
        ("2024-11-27T12:00:00Z", None),
    ],
)
def test_declared_holiday_calendar_uses_utc_dates(timestamp, expected):
    assert excluded_holiday(pd.Timestamp(timestamp)) == expected
