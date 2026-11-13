"""Diagnostic statistics for P01; missing baseline evidence stays missing."""

import numpy as np


def monthly_bootstrap(values, labels, *, calendar, resamples, seed):
    values = np.asarray(values, dtype=float)
    labels = np.asarray(labels, dtype=str)
    calendar = np.asarray(calendar, dtype=str)
    if (
        values.ndim != 1
        or not len(values)
        or len(values) != len(labels)
        or not np.isfinite(values).all()
        or not len(calendar)
        or len(set(calendar)) != len(calendar)
        or not np.isin(labels, calendar).all()
        or resamples < 2
    ):
        raise ValueError("Finite returns and a unique containing calendar are required")
    sums = np.array([values[labels == m].sum() for m in calendar])
    counts = np.array([np.sum(labels == m) for m in calendar])
    rng = np.random.default_rng(seed)
    means, rejected = [], 0
    while len(means) < resamples:
        sampled = rng.integers(len(calendar), size=len(calendar))
        n = counts[sampled].sum()
        if not n:
            rejected += 1
            if rejected > resamples * 100:
                raise ValueError("Too few populated calendar blocks")
            continue
        means.append(sums[sampled].sum() / n)
    return dict(
        mean_r=float(values.mean()),
        lower_5pct_r=float(np.quantile(means, 0.05)),
        upper_95pct_r=float(np.quantile(means, 0.95)),
        standard_error=float(np.std(means, ddof=1)),
        months=len(calendar),
        zero_trade_months=int(np.sum(counts == 0)),
        resamples=resamples,
        seed=seed,
        empty_resamples_rejected=rejected,
    )


def chunked_drawdown(outcomes_usd, *, trades_per_year, simulations, seed, chunk_size=256):
    values = np.asarray(outcomes_usd, dtype=float)
    if (
        values.ndim != 1
        or not len(values)
        or not np.isfinite(values).all()
        or trades_per_year < 1
        or simulations < 1
        or chunk_size < 1
    ):
        raise ValueError("Finite returns and positive simulation dimensions required")
    rng = np.random.default_rng(seed)
    maxima = np.empty(simulations)
    for begin in range(0, simulations, chunk_size):
        end = min(begin + chunk_size, simulations)
        sampled = rng.choice(values, size=(end - begin, trades_per_year), replace=True)
        cumulative = np.cumsum(sampled, axis=1)
        peaks = np.maximum.accumulate(np.maximum(cumulative, 0), axis=1)
        maxima[begin:end] = (peaks - cumulative).max(axis=1)
    return dict(
        p99_drawdown_usd=float(np.quantile(maxima, 0.99)),
        median_drawdown_usd=float(np.median(maxima)),
        trades_per_year=trades_per_year,
        paths=simulations,
        seed=seed,
        chunk_size=chunk_size,
        model="IID resampling of realized net USD trades into one-year paths; no new signal simulation",
    )
