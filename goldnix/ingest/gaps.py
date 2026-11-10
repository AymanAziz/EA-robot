"""Detect session and weekend gaps in UTC H1 bars."""

from __future__ import annotations

import pandas as pd

_COLUMNS = ["gap_start", "gap_end", "gap_hours", "gap_kind"]


def _crosses_weekend(start: pd.Timestamp, end: pd.Timestamp) -> bool:
    days = pd.date_range(start.normalize(), end.normalize(), freq="D")
    return any(day.weekday() >= 5 for day in days)


def find_gaps(bars: pd.DataFrame) -> pd.DataFrame:
    """Return adjacent gaps over 4 session hours or over 60 weekend hours."""
    records = []
    timestamps = bars["timestamp_utc"]
    for start, end in zip(timestamps.iloc[:-1], timestamps.iloc[1:]):
        hours = (end - start).total_seconds() / 3600
        if hours <= 4:
            continue
        weekend = _crosses_weekend(start, end)
        threshold = 60 if weekend else 4
        if hours > threshold:
            records.append(
                {
                    "gap_start": start,
                    "gap_end": end,
                    "gap_hours": hours,
                    "gap_kind": "weekend" if weekend else "session",
                }
            )
    return pd.DataFrame.from_records(records, columns=_COLUMNS)
