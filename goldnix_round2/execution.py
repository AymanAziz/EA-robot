"""Single-layer execution with the frozen quote-side policy and closed-bar management."""

import numpy as np
import pandas as pd

from ingest.holidays import excluded_holiday
from sim.engine import TRADE_COLUMNS
from sim.policy import ExitDecision, bar_excursions, resolve_exit

PRICES = [f"{side}_{kind}" for side in ("bid", "ask") for kind in ("open", "high", "low", "close")]


def _minutes(value):
    hour, minute = map(int, value.split(":"))
    return hour * 60 + minute


class Market:
    """One immutable quote snapshot shared by strategy and random-entry simulations."""

    def __init__(self, bars, gaps=None):
        self.times = pd.DatetimeIndex(bars.timestamp_utc)
        self.prices = {name: bars[name].to_numpy(dtype=float) for name in PRICES}
        self.atr = bars.atr.to_numpy(dtype=float)
        self.era = bars.era.to_numpy()
        self.signals = bars.signal.to_numpy(dtype=int)
        self.days = self.times.asi8 // (86400 * 1_000_000_000)
        self.friday = self.times.weekday == 4
        self.minutes = self.times.hour * 60 + self.times.minute
        self.holidays = np.array([excluded_holiday(t) for t in self.times])
        self.buy_eligible = bars.get("buy_eligible", pd.Series(True, index=bars.index)).to_numpy(dtype=bool)
        self.sell_eligible = bars.get("sell_eligible", pd.Series(True, index=bars.index)).to_numpy(dtype=bool)
        self.gap_starts = np.array([], dtype=np.int64)
        self.gap_ends = np.array([], dtype=np.int64)
        if gaps is not None and len(gaps):
            self.gap_starts = pd.DatetimeIndex(gaps.gap_start).asi8
            self.gap_ends = pd.DatetimeIndex(gaps.gap_end).asi8

    def eligible(self, index, direction, config):
        if index < 0 or index >= len(self.times) - 1:
            return False
        entry = index + 1
        atr = self.atr[index]
        spread = self.prices["ask_close"][index] - self.prices["bid_close"][index]
        return bool(
            np.isfinite(atr) and atr > 0
            and not (self.friday[entry] and self.minutes[entry] >= _minutes(config["friday_no_entry_from_utc"]))
            and not (config["holiday_exclusion"] and self.holidays[index])
            and spread <= config["vol_ceiling_atr"] * atr
            and (self.buy_eligible[index] if direction == 1 else self.sell_eligible[index])
        )

    def trade(self, signal_index, direction, config):
        """One hypothetical basket; caller applies schedule-wide position and daily-halt rules."""
        if config.get("max_layers", 1) != 1:
            raise ValueError("This research engine supports one layer only")
        entry_index = signal_index + 1
        atr = float(self.atr[signal_index])
        distance = max(config["stop_atr"] * atr, config["min_distance_usd"])
        reward = distance * config["target_atr"] / config["stop_atr"]
        buy = direction == 1
        quote_side = "bid" if buy else "ask"
        anchor = self.prices[f"{quote_side}_open"][entry_index]
        entry = self.prices["ask_open" if buy else "bid_open"][entry_index]
        initial_stop = anchor - direction * distance
        stop, target = initial_stop, anchor + direction * reward
        spread = self.prices["ask_open"][entry_index] - self.prices["bid_open"][entry_index]
        mae, mfe = 0., 0.
        for index in range(entry_index, len(self.times)):
            if index > entry_index and config.get("exit_management") in {"break_even", "trail"}:
                previous_close = self.prices[f"{quote_side}_close"][index - 1]
                if direction * (previous_close - entry) >= distance:
                    proposed = entry if config["exit_management"] == "break_even" else previous_close - direction * distance
                    stop = max(stop, proposed) if buy else min(stop, proposed)
            bar = {name: values[index] for name, values in self.prices.items()}
            decision = resolve_exit(
                bar, is_buy=buy, stop=stop, target=target, fill_policy=config["fill_policy"],
                gap_policy=config["gap_policy"],
                friday_flat=bool(self.friday[index] and self.minutes[index] >= _minutes(config["friday_flat_utc"])),
            )
            bar_mae, bar_mfe = bar_excursions(bar, is_buy=buy, entry=entry, distance=distance,
                                            exit_at_open=decision.at_open if decision is not None else False)
            mae, mfe = min(mae, bar_mae), max(mfe, bar_mfe)
            if decision is None:
                if index < len(self.times) - 1:
                    continue
                decision = ExitDecision(bar[f"{quote_side}_close"], "end_of_data", False)
            gap_index = np.searchsorted(self.gap_starts, self.times[entry_index].value)
            flag = (gap_index < len(self.gap_starts) and self.gap_ends[gap_index] <= self.times[index].value)
            return {
                "era": self.era[entry_index], "entry_ts": self.times[entry_index], "exit_ts": self.times[index],
                "dir": "BUY" if buy else "SELL", "layers": 1, "entry": entry, "exit": decision.price,
                "stop": initial_stop, "target": target, "atr": atr, "spread_paid": spread,
                "r_multiple": direction * (decision.price - entry) / distance,
                "mae_r": mae, "mfe_r": mfe, "exit_reason": decision.reason, "flags": "gap_risk" if flag else "",
                "signal_index": signal_index, "entry_index": entry_index, "exit_index": index,
                "entry_day": int(self.days[entry_index]), "exit_day": int(self.days[index]),
            }
        raise ValueError("No entry bar available")


def run_managed(bars, config, *, gaps=None):
    """Simulate a chronological strategy with one position and the original UTC daily halt."""
    market = Market(bars, gaps)
    records, daily = [], {}
    entry = 1
    while entry < len(market.times):
        index = entry - 1
        direction = int(market.signals[index])
        if (direction not in (-1, 1) or not market.eligible(index, direction, config)
                or daily.get(int(market.days[entry]), 0.) <= config["daily_halt_r"]):
            entry += 1
            continue
        trade = market.trade(index, direction, config)
        records.append(trade)
        day = trade["exit_day"]
        daily[day] = daily.get(day, 0.) + trade["r_multiple"]
        entry = trade["exit_index"] + 1
    return pd.DataFrame.from_records(records, columns=TRADE_COLUMNS)
