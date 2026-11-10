"""Compare Python ATR candidates with exported MT5 iATR values."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from params.atr import atr_simple, atr_wilder

METAQUOTES_DEMO_TIMEZONE = ZoneInfo("Europe/Helsinki")


@dataclass(frozen=True)
class AtrParityResult:
    simple_max_abs_difference: float
    wilder_max_abs_difference: float
    chosen_method: str | None
    passed: bool


def convert_server_time_to_utc(server_time: pd.Series) -> pd.Series:
    """Convert MetaQuotes-Demo EET/EEST labels with the European DST table."""
    parsed = pd.to_datetime(server_time, errors="raise")
    if parsed.dt.tz is not None:
        raise ValueError("server_time must contain timezone-naive MT5 labels")
    return parsed.dt.tz_localize(
        METAQUOTES_DEMO_TIMEZONE,
        ambiguous="raise",
        nonexistent="raise",
    ).dt.tz_convert("UTC")


def load_mt5_export(path: str | Path) -> pd.DataFrame:
    """Load an MT5 ATR export while keeping broker server time timezone-naive."""
    exported = pd.read_csv(path)
    exported["server_time"] = pd.to_datetime(
        exported["server_time"],
        format="%Y.%m.%d %H:%M:%S",
        errors="raise",
    )
    if not exported["compare"].isin([0, 1]).all():
        raise ValueError("compare must contain only 0 or 1")
    exported["compare"] = exported["compare"].astype(bool)
    return exported.sort_values("server_time", kind="stable").reset_index(drop=True)


def compare_atr_methods(
    exported: pd.DataFrame,
    *,
    period: int = 14,
    tolerance: float = 0.01,
) -> AtrParityResult:
    """Select the closest ATR method only when its max error is below tolerance."""
    high = exported["high"].to_numpy(dtype=float)
    low = exported["low"].to_numpy(dtype=float)
    close = exported["close"].to_numpy(dtype=float)
    mt5 = exported["mt5_atr"].to_numpy(dtype=float)
    compare = exported["compare"].to_numpy(dtype=bool)

    simple = atr_simple(high, low, close, period)
    wilder = atr_wilder(high, low, close, period)
    valid = compare & np.isfinite(mt5) & np.isfinite(simple) & np.isfinite(wilder)
    if not valid.any():
        raise ValueError("no finite ATR parity rows were marked for comparison")

    simple_difference = float(np.max(np.abs(simple[valid] - mt5[valid])))
    wilder_difference = float(np.max(np.abs(wilder[valid] - mt5[valid])))
    candidates = {
        method: difference
        for method, difference in (
            ("simple", simple_difference),
            ("wilder", wilder_difference),
        )
        if difference < tolerance
    }
    chosen = min(candidates, key=candidates.get) if candidates else None
    return AtrParityResult(
        simple_max_abs_difference=simple_difference,
        wilder_max_abs_difference=wilder_difference,
        chosen_method=chosen,
        passed=chosen is not None,
    )
