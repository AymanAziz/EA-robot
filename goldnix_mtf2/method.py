"""Closed-bar confirmation windows and symmetric bounded-risk execution."""

import numpy as np
import pandas as pd

from goldnix_mtf.method import available_rows
from ingest.holidays import excluded_holiday


def confirmation_signals(bars, prepared, kind, protocol):
    m15, h1 = prepared["m15"], prepared["h1"]
    hi = available_rows(m15.available_at, h1)
    epochs = bars.epoch_seconds.to_numpy()
    close, low, high = (bars[f"bid_{k}"].to_numpy() for k in ("close", "low", "high"))
    bid_open, ask_open = bars.bid_open.to_numpy(), bars.ask_open.to_numpy()
    spread = (bars.ask_close - bars.bid_close).to_numpy()
    output = np.zeros(len(bars), dtype=np.int8)
    audits = []
    for n, setup in enumerate(m15.itertuples()):
        if n < 499 or hi[n] < 0:
            continue
        d = int(h1.direction.iloc[hi[n]])
        if not (setup.bid_low <= setup.ema < setup.bid_close if d == 1
                else setup.bid_high >= setup.ema > setup.bid_close if d == -1 else False):
            continue
        stamp = setup.available_at.value // 10**9
        origin = int(np.searchsorted(epochs, stamp - 300))
        if origin >= len(bars) or epochs[origin] != stamp - 300 or not prepared["ready"][origin]:
            continue
        level = setup.bid_high if d == 1 else setup.bid_low
        atr = prepared["atr"][origin]
        buffer = max(spread[origin], .1 * atr)
        invalidation = setup.bid_low - buffer if d == 1 else setup.bid_high + buffer
        broken = False
        reason = "expired_without_confirmation"
        signal_index = -1
        for step in range(1, protocol["confirmation_window_m5_bars"] + 1):
            j = origin + step
            if j >= len(bars) or epochs[j] != epochs[origin] + step * 300:
                reason = "missing_bar"
                break
            if prepared["h1_direction"][j] != d or not prepared["ready"][j]:
                reason = "trend_or_history_invalid"
                break
            extreme = low[j] if d == 1 else high[j]
            if d * (extreme - invalidation) < 0:
                reason = "setup_invalidated"
                break
            extension = d * (close[j] - level)
            if not broken:
                if extension > buffer:
                    broken = True
                continue
            if extension < -buffer:
                reason = "break_failed"
                break
            touched = d * (extreme - level)
            pattern = touched <= buffer if kind == "retest" else touched >= -buffer
            if pattern and buffer < extension <= atr:
                entry = j + 1
                if entry >= len(bars) or epochs[entry] != epochs[j] + 300:
                    reason = "missing_entry_quote"
                else:
                    anchor = bid_open[entry] if d == 1 else ask_open[entry]
                    if not buffer < d * (anchor - level) <= atr:
                        reason = "entry_quote_outside_band"
                    elif output[j] != 0:
                        reason = "earlier_setup_same_entry"
                    else:
                        output[j] = d
                        signal_index = j
                        reason = "confirmed"
                break
        audits.append({"setup_available_at": setup.available_at, "direction": d, "level": level,
                       "invalidation": invalidation, "buffer": buffer, "setup_atr": atr,
                       "signal_index": signal_index, "reason": reason})
    return output, pd.DataFrame(audits)


class Market:
    """Immutable historical quotes; geometry and fill engine shared with baselines."""

    def __init__(self, bars, prepared, protocol):
        self.times = pd.DatetimeIndex(bars.timestamp_utc)
        self.epochs = bars.epoch_seconds.to_numpy()
        self.p = {f"{s}_{k}": bars[f"{s}_{k}"].to_numpy() for s in ("bid", "ask")
                  for k in ("open", "high", "low", "close")}
        self.atr, self.ready, self.protocol = prepared["atr"], prepared["ready"], protocol
        self.spread = self.p["ask_open"] - self.p["bid_open"]
        self.days = self.epochs // 86400
        day_times = pd.to_datetime(np.unique(self.days), unit="D", utc=True)
        forbidden = [int(day.value // (86400 * 10**9)) for day in day_times if excluded_holiday(day)]
        self.holidays = np.isin(self.days, forbidden)
        self.friday = self.times.weekday == 4
        self.minutes = self.times.hour * 60 + self.times.minute

    def eligible(self, entries, direction, candidate):
        """Return entry-known risk/cost eligibility and nominal stop geometry."""
        entries = np.asarray(entries, dtype=int)
        previous = entries - 1
        side = "bid" if direction == 1 else "ask"
        anchor = self.p[f"{side}_open"][entries]
        extreme = self.p[f"{side}_{'low' if direction == 1 else 'high'}"][previous]
        structure = direction * (anchor - extreme) + .1 * self.atr[previous]
        distance = np.maximum.reduce([candidate["stop_atr"] * self.atr[previous], structure,
                                       np.full(len(entries), .5)])
        spread = self.spread[entries]
        allowed = (self.ready[previous] & (self.epochs[entries] - self.epochs[previous] == 300)
            & np.isfinite(distance) & (distance > 0) & (spread >= 0)
            & (spread <= 2. + 1e-10) & (spread <= .2 * distance + 1e-10)
            & ((distance + spread) * self.protocol["usd_per_price_unit"] <= self.protocol["cash_risk_cap_usd"] + 1e-12)
            & ~(self.friday[entries] & (self.minutes[entries] >= 19 * 60)) & ~self.holidays[entries])
        return allowed, distance

    def trade(self, entry_index, direction, distance, candidate, era, last_index, fill_policy="stop_first"):
        side = "bid" if direction == 1 else "ask"
        quote = self.p[f"{side}_open"]
        anchor = quote[entry_index]
        entry = self.p["ask_open" if direction == 1 else "bid_open"][entry_index]
        stop = anchor - direction * distance
        reward = candidate["reward_r"]
        target = anchor + direction * distance * reward if reward is not None else None
        deadline = self.epochs[entry_index] + candidate["max_hold_minutes"] * 60
        gap, ambiguous = False, False
        for i in range(entry_index, last_index + 1):
            if i > entry_index and self.epochs[i] - self.epochs[i - 1] > 300:
                gap = True
            at_open = True
            if self.epochs[i] >= deadline:
                exit_price, reason = quote[i], "time_exit"
            elif self.friday[i] and self.minutes[i] >= 20 * 60:
                exit_price, reason = quote[i], "friday_flat"
            elif direction * (quote[i] - stop) < 0:
                exit_price, reason = quote[i], "gap_stop"
            elif target is not None and direction * (quote[i] - target) > 0:
                exit_price, reason = target, "gap_target"
            else:
                adverse = self.p[f"{side}_{'low' if direction == 1 else 'high'}"][i]
                favorable = self.p[f"{side}_{'high' if direction == 1 else 'low'}"][i]
                hit_stop = direction * (adverse - stop) <= 0
                hit_target = target is not None and direction * (favorable - target) >= 0
                at_open = False
                if hit_stop and not (hit_target and fill_policy == "target_first"):
                    exit_price, reason = stop, "stop"
                elif hit_target:
                    exit_price, reason = target, "target"
                elif i == last_index:
                    exit_price, reason = self.p[f"{side}_close"][i], "era_end"
                else:
                    continue
                ambiguous = bool(hit_stop and hit_target)
            return {"era": era, "dir": "BUY" if direction == 1 else "SELL",
                "signal_index": entry_index - 1, "entry_index": entry_index, "exit_index": i,
                "entry_ts": self.times[entry_index], "exit_ts": self.times[i],
                "entry_day": int(self.days[entry_index]), "exit_day": int(self.days[i]),
                "entry": float(entry), "exit": float(exit_price), "stop": float(stop), "target": target,
                "distance": float(distance), "atr": float(self.atr[entry_index - 1]),
                "spread_paid": float(self.spread[entry_index]),
                "r_multiple": float(direction * (exit_price - entry) / distance),
                "pnl_usd": float(direction * (exit_price - entry) * self.protocol["usd_per_price_unit"]),
                "exit_reason": reason, "ambiguous_exit_bar": ambiguous,
                "exit_time_precision": "observed_open" if at_open else "M5_bar_label",
                "flags": "gap_risk" if gap else ""}
        raise ValueError("No exit quote inside era")

    def simulate(self, signal, candidate, era, bounds, fill_policy="stop_first"):
        start, end = map(pd.Timestamp, bounds)
        first, final = self.times.searchsorted(start), self.times.searchsorted(end) - 1
        entries = np.flatnonzero(signal) + 1
        entries = entries[(entries >= max(first, 1)) & (entries < final)]
        directions = signal[entries - 1]
        records, daily, last_exit = [], {}, -1
        for d in (1, -1):
            ids = entries[directions == d]
            allowed, distances = self.eligible(ids, d, candidate)
            records.extend((int(i), d, float(s)) for i, s in zip(ids[allowed], distances[allowed]))
        trades = []
        for i, d, distance in sorted(records):
            if i <= last_exit or daily.get(int(self.days[i]), 0.) <= self.protocol["daily_halt_r"]:
                continue
            trade = self.trade(i, d, distance, candidate, era, final, fill_policy)
            trades.append(trade)
            last_exit = trade["exit_index"]
            daily[trade["exit_day"]] = daily.get(trade["exit_day"], 0.) + trade["r_multiple"]
        return pd.DataFrame(trades)

    def pool(self, candidate, era, bounds, wanted_directions):
        start, end = map(pd.Timestamp, bounds)
        first, final = self.times.searchsorted(start), self.times.searchsorted(end) - 1
        entries = np.arange(max(1, first), final)
        records = []
        for d in wanted_directions:
            allowed, distances = self.eligible(entries, d, candidate)
            for i, distance in zip(entries[allowed], distances[allowed]):
                records.append(self.trade(int(i), d, float(distance), candidate, era, final))
        return pd.DataFrame(records)
