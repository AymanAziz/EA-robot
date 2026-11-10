"""Freeze-gated holdout ingestion."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from gates.freeze import assert_holdout_unlocked
from ingest.ingest import load_bars


def load_holdout(path: str | Path, *, root: str | Path) -> pd.DataFrame:
    """Load holdout bars only when config and research code match the freeze."""
    assert_holdout_unlocked(root)
    return load_bars(path)
