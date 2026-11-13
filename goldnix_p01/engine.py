"""Independent chronological execution model in USC (100 USC = 1 USD).

Broker applies server stops on every quote before a later timer decision.
Historical costs, session metadata and money precision are explicit inputs.
"""

from dataclasses import dataclass, replace
import math

from .policy import Protection, plan_protection


@dataclass(frozen=True)
class Contract:
    tick: float = 0.01
    stops: float = 0.0
    freeze: float = 0.0
    exposure_usc_per_price: float = 1.0
    money_quantum: float = 0.01
    initial_equity: float = 2000.0
    round_trip_cost: float = 0.0
    leverage: float = 100.0
    stop_fill: str = "quote"
    target_fill: str = "level"
    protection_enabled: bool = True

    def __post_init__(self):
        positive = (
            self.tick,
            self.exposure_usc_per_price,
            self.money_quantum,
            self.initial_equity,
            self.leverage,
        )
        nonnegative = (self.stops, self.freeze, self.round_trip_cost)
        if (
            not all(math.isfinite(x) and x > 0 for x in positive)
            or not all(math.isfinite(x) and x >= 0 for x in nonnegative)
            or self.stop_fill not in ("quote", "level")
            or self.target_fill not in ("quote", "level")
        ):
            raise ValueError("Invalid broker execution contract")


def grid(value, tick):
    return math.floor(value / tick + 0.5 + 1e-9) * tick


class Broker:
    def __init__(self, contract):
        self.contract = contract
        self.position = None
        self.trades = []
        self.updates = []
        self.balance = contract.initial_equity

    def open(self, *, side, utc, bid, ask, distance, atr):
        if self.position is not None or side not in (-1, 1) or distance <= 0 or bid <= 0 or ask < bid:
            raise ValueError("Invalid or overlapping entry")
        anchor, entry = (bid, ask) if side == 1 else (ask, bid)
        stop = grid(anchor - side * distance, self.contract.tick)
        target = grid(anchor + side * 3 * distance, self.contract.tick)
        self.position = dict(
            side=side,
            entry_utc=utc,
            entry=entry,
            atr=atr,
            distance=distance,
            initial_sl=stop,
            tp=target,
            last_request=0,
            close_requested=False,
            protection=Protection(side, entry, stop, target, entry, stop),
        )

    def quote(self, utc_ms, *, bid, ask):
        if self.position is None:
            return
        p = self.position
        price = bid if p["side"] == 1 else ask
        stop = p["protection"].accepted_stop
        epsilon = self.contract.tick * 1e-6  # Compare decimal broker grid equality.
        if p["side"] * (price - stop) <= epsilon:
            self.close(utc_ms / 1000, stop if self.contract.stop_fill == "level" else price, "sl")
        elif p["side"] * (price - p["tp"]) >= -epsilon:
            self.close(utc_ms / 1000, price if self.contract.target_fill == "quote" else p["tp"], "tp")

    def close(self, utc, price, reason):
        if self.position is None:
            return
        p = self.position
        gain = p["side"] * (price - p["entry"])
        gross = gain * self.contract.exposure_usc_per_price
        pnl = (
            math.copysign(math.floor(abs(gross) / self.contract.money_quantum + 0.5 + 1e-9), gross)
            * self.contract.money_quantum
        )
        pnl -= self.contract.round_trip_cost
        self.balance += pnl
        self.trades.append(
            {k: v for k, v in p.items() if k not in ("protection", "last_request", "close_requested")}
            | dict(
                exit_utc=utc,
                exit=price,
                exit_reason=reason,
                pnl_usc=pnl,
                r_multiple=gain / p["distance"],
                peak=p["protection"].peak,
                accepted_sl=p["protection"].accepted_stop,
            )
        )
        self.position = None

    def protect(self, utc, *, bid, ask):
        if self.position is None or not self.contract.protection_enabled:
            return
        p, c = self.position, self.contract
        decision = plan_protection(
            p["protection"],
            bid=bid,
            ask=ask,
            tick=c.tick,
            stops=c.stops,
            freeze=c.freeze,
            costs=(c.round_trip_cost + 0.2) / c.exposure_usc_per_price,
        )
        p["protection"] = replace(p["protection"], peak=decision.peak)
        p["close_requested"] |= decision.action == "exit"
        if utc - p["last_request"] < 2:
            return
        if p["close_requested"]:
            p["last_request"] = utc
            self.close(utc, bid if p["side"] == 1 else ask, "profit_floor")
        elif decision.action == "modify":
            p["last_request"] = utc
            p["protection"] = replace(p["protection"], accepted_stop=decision.stop)
            self.updates.append(dict(utc=utc, stop=decision.stop, peak=decision.peak))

    def equity(self, bid, ask):
        if self.position is None:
            return self.balance
        p = self.position
        gross = (
            p["side"] * ((bid if p["side"] == 1 else ask) - p["entry"]) * self.contract.exposure_usc_per_price
        )
        return (
            self.balance
            + math.copysign(math.floor(abs(gross) / self.contract.money_quantum + 0.5 + 1e-9), gross)
            * self.contract.money_quantum
        )
