"""Calendar-month block bootstrap for trade-level R outcomes."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class BootstrapResult:
    point_estimate: float
    standard_error: float
    lower_bound: float
    resamples: int
    edge_point_estimate: float | None
    edge_lower_bound: float | None


def monthly_block_bootstrap(
    trades: pd.DataFrame,
    *,
    value_column: str = "r_multiple",
    timestamp_column: str = "exit_ts",
    resamples: int = 10_000,
    seed: int,
    baseline_draw_means=None,
) -> BootstrapResult:
    """Resample whole calendar months and return a one-sided 5% lower bound."""
    if trades.empty:
        raise ValueError("monthly bootstrap requires at least one trade")
    if resamples < 2:
        raise ValueError("resamples must be at least 2")
    timestamps = pd.to_datetime(trades[timestamp_column], utc=True, errors="raise")
    values = trades[value_column].to_numpy(dtype=float)
    month_labels = timestamps.dt.strftime("%Y-%m").to_numpy()
    blocks = [values[month_labels == month] for month in pd.unique(month_labels)]
    rng = np.random.default_rng(seed)
    sample_means = np.empty(resamples, dtype=float)
    for index in range(resamples):
        selected = rng.integers(0, len(blocks), size=len(blocks))
        sample = np.concatenate([blocks[block] for block in selected])
        sample_means[index] = sample.mean()

    edge_point = None
    edge_lower = None
    if baseline_draw_means is not None:
        baseline = np.asarray(baseline_draw_means, dtype=float)
        if baseline.ndim != 1 or baseline.size == 0 or not np.isfinite(baseline).all():
            raise ValueError("baseline_draw_means must be a finite non-empty 1-D array")
        sampled_baseline = rng.choice(baseline, size=resamples, replace=True)
        edge_samples = sample_means - sampled_baseline
        edge_point = float(values.mean() - baseline.mean())
        edge_lower = float(np.quantile(edge_samples, 0.05))

    return BootstrapResult(
        point_estimate=float(values.mean()),
        standard_error=float(sample_means.std(ddof=1)),
        lower_bound=float(np.quantile(sample_means, 0.05)),
        resamples=resamples,
        edge_point_estimate=edge_point,
        edge_lower_bound=edge_lower,
    )
