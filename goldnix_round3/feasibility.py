"""Exact loss-run bounds under the frozen IID annual drawdown model."""

import math

import numpy as np


def run_probability(probability, trades, length):
    """Probability of at least one run of length successes in independent draws."""
    if not 0 <= probability <= 1 or trades < 0 or length < 1:
        raise ValueError("Invalid probability or run dimensions")
    if length > trades:
        return 0.
    states = np.zeros(length)
    states[0] = 1.
    breach = 0.
    for _ in range(trades):
        breach += states[-1] * probability
        updated = np.zeros(length)
        updated[0] = states.sum() * (1 - probability)
        updated[1:] = states[:-1] * probability
        states = updated
    return float(min(1., breach))


def drawdown_lower_bound(pnl, *, annual_trades, limit_usd):
    """Bound drawdown breach by runs of losses, without assuming recovery gains.

    Each selected loss has magnitude >= threshold. A run whose sum exceeds the
    limit necessarily causes a drawdown breach. Maximising these separate lower
    bounds remains a valid lower bound; they are not added as independent events.
    Failure applies only to this empirical IID model, not every possible strategy.
    """
    pnl = np.asarray(pnl, dtype=float)
    if not len(pnl) or not np.isfinite(pnl).all() or annual_trades < 1 or limit_usd <= 0:
        raise ValueError("Finite P/L, positive annual count and positive limit required")
    losses = -pnl[pnl < 0]
    # Fixed ladder plus observed loss quantiles. It is a lower bound, not an
    # exhaustive calculation of all possible mixed-loss drawdown paths.
    thresholds = np.unique(np.r_[np.array([.25, .5, .75, 1., 1.5, 2., limit_usd]),
                                np.quantile(losses, np.linspace(0, 1, 21)) if len(losses) else []])
    best = {"breach_probability_lower_bound": 0., "loss_threshold_usd": None,
            "consecutive_losses": None, "one_draw_loss_probability": 0.}
    for threshold in thresholds:
        length = math.floor(limit_usd / threshold) + 1
        if length * threshold <= limit_usd or math.isclose(length * threshold, limit_usd, rel_tol=1e-12):
            length += 1
        probability = float(np.mean(pnl <= -threshold))
        bound = run_probability(probability, annual_trades, length)
        if bound > best["breach_probability_lower_bound"]:
            best = {"breach_probability_lower_bound": bound, "loss_threshold_usd": float(threshold),
                    "consecutive_losses": length, "one_draw_loss_probability": probability}
    return {**best, "annual_trades": annual_trades, "limit_usd": limit_usd,
            "g7_mathematically_incompatible_with_iid_distribution": best["breach_probability_lower_bound"] > .01,
            "approval": False, "model": "Fixed empirical IID annual P/L draws, same assumption as frozen G7"}
