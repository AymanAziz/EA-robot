"""Causal H4 context and M15/M5 failure confirmation around frozen H1 levels."""

import numpy as np
import pandas as pd

from goldnix_mtf.method import aggregate, ema
from goldnix_mtf2.method import Market


def prepare_context(bars):
    epochs = bars.epoch_seconds.to_numpy()
    if len(epochs) == 0 or np.any(np.diff(epochs) <= 0) or np.any(epochs % 300):
        raise ValueError("Unique chronological M5 grid required")
    if not np.array_equal(pd.DatetimeIndex(bars.timestamp_utc).asi8 // 10**9, epochs):
        raise ValueError("Timestamp and epoch disagree")
    higher = aggregate(bars, 240)
    close = (higher.bid_close + higher.ask_close).to_numpy() / 2
    average = ema(close, 50)
    slope = average - pd.Series(average).shift(3).to_numpy()
    direction = np.select([(close > average) & (slope > 0), (close < average) & (slope < 0)], [1, -1], 0)
    available = pd.DatetimeIndex(higher.available_at).asi8 // 10**9
    index = np.searchsorted(available, epochs, side="right") - 1
    ready, mapped, stamps = np.zeros(len(bars), bool), np.zeros(len(bars), int), np.full(len(bars), -1)
    if len(higher):
        safe = np.maximum(index, 0)
        age = epochs - available[safe]
        ready = (index >= 99) & (age >= 0) & (age < 14400)
        mapped = np.where(ready, direction[safe], 0)
        stamps = np.where(index >= 0, available[safe], -1)
    # A complete M15 close is known only after its final M5 bar closes.
    m15_complete = np.zeros(len(bars), bool)
    if len(bars) >= 3:
        m15_complete[2:] = ((epochs[2:] + 300) % 900 == 0) & (epochs[2:] - epochs[:-2] == 600)
    return {"h4_ready": ready, "h4_direction": mapped, "h4_available_at": stamps,
            "m15_complete_at_close": m15_complete,
            "mid_close": (bars.bid_close + bars.ask_close).to_numpy() / 2}


class FakeoutMarket(Market):
    """Keep frozen fills; a causal failure exit may precede the fixed exit."""

    def __init__(self, bars, prepared, protocol):
        super().__init__(bars, prepared, protocol)
        self.context = prepare_context(bars)

    def trade(self, entry_index, direction, distance, candidate, era, last_index,
              fill_policy="stop_first", *, fakeout=False, level=None, buffer=None):
        original = super().trade(entry_index, direction, distance, candidate, era, last_index, fill_policy)
        if not fakeout:
            return original
        if level is None or buffer is None or not np.isfinite([level, buffer]).all() or buffer < 0:
            raise ValueError("Entry-known finite frozen level and nonnegative buffer required")
        end = original["exit_index"]
        side = "bid" if direction == 1 else "ask"
        close = self.context["mid_close"]
        warning = None
        for index in range(entry_index, end):
            if warning is not None:
                consecutive = self.epochs[index] == self.epochs[warning] + 300
                if consecutive and direction * (close[index] - level) < -buffer:
                    exit_index = index + 1
                    quote = float(self.p[f"{side}_open"][exit_index])
                    # A recorded fixed exit at this open, or an already-hit
                    # barrier, precedes discretionary failure management.
                    barrier_hit = (direction * (quote - original["stop"]) <= 0
                                   or direction * (quote - original["target"]) >= 0)
                    if exit_index == end and (original["exit_time_precision"] == "observed_open" or barrier_hit):
                        return original
                    gap = bool(np.any(np.diff(self.epochs[entry_index:exit_index + 1]) > 300))
                    return original | {
                        "exit_index": exit_index, "exit_ts": self.times[exit_index],
                        "exit_day": int(self.days[exit_index]), "exit": quote,
                        "r_multiple": float(direction * (quote - original["entry"]) / distance),
                        "pnl_usd": float(direction * (quote - original["entry"]) * self.protocol["usd_per_price_unit"]),
                        "exit_reason": "fakeout_confirmed", "exit_time_precision": "observed_open",
                        "ambiguous_exit_bar": False, "flags": "gap_risk" if gap else "",
                        "warning_index": warning, "confirmation_index": index,
                    }
                warning = None
            if (index >= entry_index + 2 and self.context["m15_complete_at_close"][index]
                    and self.epochs[index - 2] >= self.epochs[entry_index]
                    and direction * (close[index] - level) < -buffer):
                warning = index
        return original
