"""Detect sustained provider-volume unit changes from local medians."""

from __future__ import annotations

import numpy as np
import pandas as pd

_COLUMNS = [
    "boundary_index",
    "boundary_ts",
    "before_median",
    "after_median",
    "ratio",
    "direction",
    "qualifying_bars",
]


def _ratio(after: float, before: float) -> float:
    if before == 0:
        return np.inf if after > 0 else np.nan
    return after / before


def _strength(ratio: float) -> float:
    if ratio == 0 or not np.isfinite(ratio):
        return np.inf
    return abs(np.log(ratio))


def find_volume_boundaries(
    bars: pd.DataFrame,
    *,
    window: int = 500,
    hold: int = 50,
) -> pd.DataFrame:
    """Consolidate sustained >5x or <0.2x local median ratios into boundaries."""
    candidates = []
    volume = bars["provider_volume"].to_numpy(dtype=float)
    for index in range(window, len(volume) - window + 1):
        before = float(np.median(volume[index - window:index]))
        after = float(np.median(volume[index:index + window]))
        ratio = _ratio(after, before)
        direction = "up" if ratio > 5 else "down" if ratio < 0.2 else None
        if direction is not None:
            candidates.append(
                {
                    "boundary_index": index,
                    "boundary_ts": bars.iloc[index]["timestamp_utc"],
                    "before_median": before,
                    "after_median": after,
                    "ratio": ratio,
                    "direction": direction,
                }
            )

    records = []
    run = []
    for candidate in candidates + [None]:
        continues = (
            candidate is not None
            and run
            and candidate["direction"] == run[-1]["direction"]
            and candidate["boundary_index"] == run[-1]["boundary_index"] + 1
        )
        if candidate is not None and (not run or continues):
            run.append(candidate)
            continue
        if len(run) >= hold:
            strongest = max(_strength(item["ratio"]) for item in run)
            tied = [item for item in run if _strength(item["ratio"]) == strongest]
            selected = tied[len(tied) // 2].copy()
            selected["qualifying_bars"] = len(run)
            records.append(selected)
        run = [] if candidate is None else [candidate]

    return pd.DataFrame.from_records(records, columns=_COLUMNS)
