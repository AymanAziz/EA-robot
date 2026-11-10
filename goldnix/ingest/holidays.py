"""UTC calendar-day exclusions declared by the decision configuration."""

from __future__ import annotations

from datetime import date, timedelta

from dateutil.easter import easter


def _thanksgiving(year: int) -> date:
    november_first = date(year, 11, 1)
    first_thursday = november_first + timedelta(days=(3 - november_first.weekday()) % 7)
    return first_thursday + timedelta(weeks=3)


def excluded_holiday(timestamp) -> str | None:
    """Return the exclusion name for a UTC timestamp, or None when eligible."""
    day = timestamp.date()
    if (day.month, day.day) in {(12, 24), (12, 25), (12, 26)}:
        return "christmas_closure"
    if (day.month, day.day) == (1, 1):
        return "new_years_day"
    if day == easter(day.year) - timedelta(days=2):
        return "good_friday"
    if day == _thanksgiving(day.year):
        return "us_thanksgiving"
    return None
