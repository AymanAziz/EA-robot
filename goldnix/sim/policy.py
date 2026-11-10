"""Deterministic quote-side exit policy for one H1 position."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class ExitDecision:
    price: float
    reason: str
    at_open: bool


def resolve_exit(
    bar: pd.Series,
    *,
    is_buy: bool,
    stop: float,
    target: float,
    fill_policy: str,
    gap_policy: str,
    friday_flat: bool,
) -> ExitDecision | None:
    """Resolve the first modelled exit for one bar under the declared policies."""
    market_open = float(bar["bid_open"] if is_buy else bar["ask_open"])
    if friday_flat:
        return ExitDecision(market_open, "friday_flat", True)

    adverse_gap = (is_buy and market_open < stop) or (
        not is_buy and market_open > stop
    )
    if adverse_gap:
        return ExitDecision(market_open, "gap_stop", True)

    favourable_gap = (is_buy and market_open > target) or (
        not is_buy and market_open < target
    )
    if favourable_gap:
        price = market_open if gap_policy == "both_at_open" else target
        return ExitDecision(price, "gap_target", True)

    if is_buy:
        stop_hit = float(bar["bid_low"]) <= stop
        target_hit = float(bar["bid_high"]) >= target
    else:
        stop_hit = float(bar["ask_high"]) >= stop
        target_hit = float(bar["ask_low"]) <= target

    if not stop_hit and not target_hit:
        return None
    if stop_hit and not (target_hit and fill_policy == "target_first"):
        return ExitDecision(stop, "stop", False)
    return ExitDecision(target, "target", False)


def bar_excursions(
    bar: pd.Series,
    *,
    is_buy: bool,
    entry: float,
    distance: float,
    exit_at_open: bool,
) -> tuple[float, float]:
    """Return adverse and favourable R excursions while the trade is modelled open."""
    if exit_at_open:
        market_open = float(bar["bid_open"] if is_buy else bar["ask_open"])
        value = (
            (market_open - entry) / distance
            if is_buy
            else (entry - market_open) / distance
        )
        return value, value
    if is_buy:
        return (
            (float(bar["bid_low"]) - entry) / distance,
            (float(bar["bid_high"]) - entry) / distance,
        )
    return (
        (entry - float(bar["ask_high"])) / distance,
        (entry - float(bar["ask_low"])) / distance,
    )
