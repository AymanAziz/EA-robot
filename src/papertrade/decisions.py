from __future__ import annotations

import math
from dataclasses import dataclass

from papertrade.config import Settings
from papertrade.domain import Instrument, Quote


@dataclass(frozen=True)
class Decision:
    action: str
    reason: str
    cost_bps: float


def decide(probability: float, expected_return: float, regime: str, instrument: Instrument,
           quote: Quote, volume: float, held_qty: float, settings: Settings) -> Decision:
    cost = 2 * instrument.fee_bps + 2 * instrument.slippage_bps + quote.spread_bps
    if not all(math.isfinite(v) for v in (probability, expected_return, volume, cost)):
        return Decision("HOLD", "invalid_prediction", cost)
    if held_qty > 0:
        if probability < 0.45 or expected_return * 10000 < -cost:
            return Decision("CLOSE", "exit_prediction", cost)
        return Decision("HOLD", "position_already_open", cost)
    if not quote.tradeable or volume < instrument.min_volume:
        return Decision("HOLD", "insufficient_liquidity", cost)
    if regime in {"high_volatility", "volatile", "unknown"}:
        return Decision("HOLD", "unsupported_regime", cost)
    if probability < settings.min_probability:
        return Decision("HOLD", "probability_below_threshold", cost)
    if expected_return * 10000 <= cost + settings.min_net_edge_bps:
        return Decision("HOLD", "no_edge_after_costs", cost)
    return Decision("BUY", "validated_edge_after_costs", cost)
