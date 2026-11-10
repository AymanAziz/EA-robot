"""Monte Carlo account-risk simulation from observed trade P/L."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class MonteCarloResult:
    p99_max_drawdown_usd: float
    trades_per_year: int
    simulations: int


def max_drawdown(pnl) -> float:
    """Return maximum peak-to-trough drawdown, including starting equity."""
    pnl = np.asarray(pnl, dtype=float)
    cumulative = np.concatenate(([0.0], np.cumsum(pnl)))
    peaks = np.maximum.accumulate(cumulative)
    return float(np.max(peaks - cumulative))


def monte_carlo_drawdown(
    observed_pnl,
    *,
    trades_per_year: int,
    simulations: int,
    seed: int,
) -> MonteCarloResult:
    """Resample observed USD trade outcomes into one-year paths."""
    outcomes = np.asarray(observed_pnl, dtype=float)
    if outcomes.ndim != 1 or outcomes.size == 0 or not np.isfinite(outcomes).all():
        raise ValueError("observed_pnl must be a finite non-empty 1-D array")
    if trades_per_year < 1 or simulations < 1:
        raise ValueError("trades_per_year and simulations must be positive")
    rng = np.random.default_rng(seed)
    sampled = rng.choice(outcomes, size=(simulations, trades_per_year), replace=True)
    cumulative = np.cumsum(sampled, axis=1)
    cumulative = np.concatenate([np.zeros((simulations, 1)), cumulative], axis=1)
    peaks = np.maximum.accumulate(cumulative, axis=1)
    path_drawdowns = np.max(peaks - cumulative, axis=1)
    return MonteCarloResult(
        p99_max_drawdown_usd=float(np.quantile(path_drawdowns, 0.99)),
        trades_per_year=trades_per_year,
        simulations=simulations,
    )
