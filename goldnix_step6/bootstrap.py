"""Calendar-aligned block bootstrap for a strategy and random baseline paths."""

from __future__ import annotations

import numpy as np
import pandas as pd


def paired_month_bootstrap(signal, baseline, *, start, end, resamples, seed):
    """Resample identical calendar months for both arms, including inactive months."""
    if signal.empty or baseline.empty or resamples < 2:
        raise ValueError("Nonempty strategy/baseline and at least two resamples required")
    months = pd.period_range(pd.Timestamp(start).strftime("%Y-%m"),
                             pd.Timestamp(end).strftime("%Y-%m"), freq="M").astype(str)
    def monthly(frame):
        labels = pd.to_datetime(frame.exit_ts, utc=True).dt.strftime("%Y-%m")
        if not labels.isin(months).all() or not np.isfinite(frame.r_multiple).all():
            raise ValueError("Trades must be finite and inside the declared calendar")
        return frame.groupby(labels).r_multiple.agg(["sum", "count"]).reindex(months, fill_value=0)
    s = monthly(signal)
    by_draw = [monthly(frame) for _, frame in baseline.groupby("draw", sort=True)]
    b_sums = np.array([frame["sum"].to_numpy() for frame in by_draw])
    b_counts = np.array([frame["count"].to_numpy() for frame in by_draw])
    s_sums, s_counts = s["sum"].to_numpy(), s["count"].to_numpy()
    rng = np.random.default_rng(seed)
    means, edges = [], []
    rejected = 0
    while len(means) < resamples:
        sampled = rng.integers(len(months), size=len(months))
        draws = rng.integers(len(by_draw), size=len(by_draw))
        sn, bn = s_counts[sampled].sum(), b_counts[:, sampled].sum(axis=1)
        if sn == 0 or np.any(bn[draws] == 0):
            rejected += 1
            if rejected > resamples * 100:
                raise ValueError("Too few populated calendar blocks")
            continue
        sm = s_sums[sampled].sum() / sn
        totals = b_sums[:, sampled].sum(axis=1)
        bm = np.mean(totals[draws] / bn[draws])
        means.append(sm)
        edges.append(sm - bm)
    baseline_mean = np.mean(b_sums.sum(axis=1) / b_counts.sum(axis=1))
    return {
        "mean_r": float(signal.r_multiple.mean()),
        "mean_lower": float(np.quantile(means, .05)),
        "standard_error": float(np.std(means, ddof=1)),
        "baseline_mean": float(baseline_mean),
        "edge_point": float(signal.r_multiple.mean() - baseline_mean),
        "edge_lower": float(np.quantile(edges, .05)),
        "months": len(months), "zero_trade_months": int((s_counts == 0).sum()),
        "resamples": resamples, "empty_resamples_rejected": rejected,
    }
