"""Independent arithmetic from the declared P01 rule, with no MQL header imports."""

from dataclasses import dataclass
import math


@dataclass(frozen=True)
class Protection:
    side: int
    entry: float
    original_stop: float
    target: float
    peak: float
    accepted_stop: float


@dataclass(frozen=True)
class Decision:
    action: str
    stop: float
    peak: float


def plan_protection(p: Protection, *, bid, ask, tick, stops, freeze, costs):
    values = (
        p.entry,
        p.original_stop,
        p.target,
        p.peak,
        p.accepted_stop,
        bid,
        ask,
        tick,
        stops,
        freeze,
        costs,
    )
    if (
        not all(math.isfinite(v) for v in values)
        or p.side not in (-1, 1)
        or min(values[:8]) <= 0
        or ask < bid
        or min(stops, freeze, costs) < 0
    ):
        raise ValueError("Invalid protection inputs")
    risk = p.side * (p.entry - p.original_stop)
    if (
        risk <= 0
        or p.side * (p.target - p.entry) <= 0
        or p.side * (p.accepted_stop - p.original_stop) < -tick * 0.01
        or p.side * (p.peak - p.entry) < -tick * 0.01
    ):
        raise ValueError("Invalid original risk or recorded protection")
    price = bid if p.side == 1 else ask
    gain = max(p.side * (p.peak - p.entry), p.side * (price - p.entry))
    peak = p.entry + p.side * gain
    if gain + tick * 1e-6 < max(risk / 2, 2 * (costs + tick)):
        return Decision("hold", p.accepted_stop, peak)
    floor_gain = max(gain / 2, costs + tick)
    unrounded = (p.entry + p.side * floor_gain) / tick
    rounding = math.ceil(unrounded - 1e-8) if p.side == 1 else math.floor(unrounded + 1e-8)
    stop = rounding * tick
    if p.side * (price - stop) <= 0:
        return Decision("exit", stop, peak)
    if p.side * (stop - p.accepted_stop) < max(tick, risk / 20) - tick * 1e-6:
        return Decision("hold", p.accepted_stop, peak)
    unavailable = p.side * (price - stop) < max(stops, freeze) + tick or p.side * (p.target - stop) <= 0
    if freeze:
        unavailable |= min(p.side * (price - p.accepted_stop), p.side * (p.target - price)) <= freeze + tick
    return Decision("blocked" if unavailable else "modify", stop, peak)
