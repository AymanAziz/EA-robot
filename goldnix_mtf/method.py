"""Causal H1/M15/M5 decisions and a symmetric five-minute quote-side simulator."""

import numpy as np
import pandas as pd

from ingest.holidays import excluded_holiday
from params.atr import atr_simple


def ema(values, period):
    values = np.asarray(values, dtype=float)
    result = np.full(len(values), np.nan)
    if len(values) >= period:
        result[period - 1] = values[:period].mean()
        alpha = 2 / (period + 1)
        for i in range(period, len(values)):
            result[i] = alpha * values[i] + (1 - alpha) * result[i - 1]
    return result


def aggregate(bars, minutes):
    """Exclude incomplete UTC buckets; an aggregate is available at its close."""
    grouped = bars.groupby(bars.timestamp_utc.dt.floor(f"{minutes}min"))
    rules = {f"{side}_{kind}": func for side in ("bid", "ask")
             for kind, func in (("open", "first"), ("high", "max"), ("low", "min"), ("close", "last"))}
    result = grouped.agg(rules)
    result = result.loc[grouped.size().eq(minutes // 5)].reset_index()
    result["available_at"] = result.timestamp_utc + pd.Timedelta(minutes=minutes)
    return result


def available_rows(decisions, higher):
    """Return last completed higher-timeframe row, never the forming bar."""
    return np.searchsorted(pd.DatetimeIndex(higher.available_at).asi8,
                           pd.DatetimeIndex(decisions).asi8, side="right") - 1


def features(bars, protocol):
    settings = protocol["signals"]
    h1, m15 = aggregate(bars, 60), aggregate(bars, 15)
    h1["ema"] = ema(h1.bid_close, settings["h1_ema_period"])
    slope = h1.ema - h1.ema.shift(settings["h1_slope_bars"])
    h1["direction"] = np.select([h1.bid_close.gt(h1.ema) & slope.gt(0),
                                  h1.bid_close.lt(h1.ema) & slope.lt(0)], [1, -1], 0)
    warmup = settings["warmup_bars_per_timeframe"]
    h1.loc[h1.index < warmup - 1, "direction"] = 0
    m15["ema"] = ema(m15.bid_close, settings["m15_ema_period"])
    decisions = bars.timestamp_utc + pd.Timedelta(minutes=5)
    hi, mi = available_rows(decisions, h1), available_rows(decisions, m15)
    safe_hi, safe_mi = np.maximum(hi, 0), np.maximum(mi, 0)
    if h1.empty or m15.empty:
        raise ValueError("Insufficient higher timeframe history")
    h1_age = pd.DatetimeIndex(decisions).asi8 - pd.DatetimeIndex(h1.available_at).asi8[safe_hi]
    m15_age = pd.DatetimeIndex(decisions).asi8 - pd.DatetimeIndex(m15.available_at).asi8[safe_mi]
    h1_ready = (hi >= warmup - 1) & (h1_age >= 0) & (h1_age < 3600 * 10**9)
    m15_ready = (mi >= warmup - 1) & (m15_age >= 0) & (m15_age < 900 * 10**9)
    atr = atr_simple(bars.bid_high, bars.bid_low, bars.bid_close, settings["atr_period"])
    contiguous = bars.epoch_seconds.diff().eq(300).rolling(settings["atr_period"]).sum()
    ready = (h1_ready & m15_ready & (np.arange(len(bars)) >= warmup - 1)
             & contiguous.eq(settings["atr_period"]).to_numpy() & np.isfinite(atr) & (atr > 0))
    return {"h1": h1, "m15": m15, "atr": atr, "ready": ready,
            "h1_direction": np.where(h1_ready, h1.direction.to_numpy()[safe_hi], 0),
            "h1_available_at": pd.DatetimeIndex(h1.available_at).asi8[safe_hi]}


def confirm(bars, setup_index, direction, level, buffer, atr, max_extension):
    """Exactly two later closed M5 bars: break, then bounded retest/reclaim."""
    a, b = setup_index + 1, setup_index + 2
    if b >= len(bars) or bars.epoch_seconds.iloc[b] - bars.epoch_seconds.iloc[setup_index] != 600:
        return "missing_confirmation_bar"
    first, second = bars.iloc[a], bars.iloc[b]
    threshold = level + direction * buffer
    if direction * (first.bid_close - threshold) <= 0:
        return "no_closing_break"
    touch = second.bid_low if direction == 1 else second.bid_high
    if not level - buffer <= touch <= level + buffer:
        return "no_bounded_retest"
    if direction * (second.bid_close - threshold) <= 0:
        return "no_reclaim"
    if direction * (second.bid_close - level) > max_extension * atr:
        return "extended_reclaim"
    return "confirmed"


def signals(bars, prepared, protocol):
    """Emit one auditable decision for every trend-aligned M15 pullback."""
    settings = protocol["signals"]
    m15, h1 = prepared["m15"], prepared["h1"]
    setup_hi = available_rows(m15.available_at, h1)
    hdir = h1.direction.to_numpy()
    epochs = bars.epoch_seconds.to_numpy()
    records = []
    signal = np.zeros(len(bars), dtype=np.int8)
    for number, row in enumerate(m15.itertuples()):
        hi = setup_hi[number]
        if number < settings["warmup_bars_per_timeframe"] - 1 or hi < 0:
            continue
        direction = int(hdir[hi])
        pullback = (row.bid_low <= row.ema < row.bid_close if direction == 1
                    else row.bid_high >= row.ema > row.bid_close if direction == -1 else False)
        if not pullback:
            continue
        t = row.available_at.value // 10**9
        j = int(np.searchsorted(epochs, t - 300))
        if j >= len(bars) or epochs[j] != t - 300 or not prepared["ready"][j]:
            continue
        if prepared["h1_direction"][j] != direction:
            continue
        level = row.bid_high if direction == 1 else row.bid_low
        atr = float(prepared["atr"][j])
        spread = float(bars.ask_close.iloc[j] - bars.bid_close.iloc[j])
        buffer = max(spread, settings["buffer_atr_fraction"] * atr)
        reason = confirm(bars, j, direction, level, buffer, atr, settings["reclaim_max_extension_atr"])
        signal_index, entry_index = j + 2, j + 3
        if reason == "confirmed":
            if entry_index >= len(bars) or epochs[entry_index] != t + 600:
                reason = "missing_entry_quote"
            elif prepared["h1_direction"][signal_index] != direction:
                reason = "trend_changed"
            else:
                anchor = (bars.bid_open.iloc[entry_index] if direction == 1
                          else bars.ask_open.iloc[entry_index])
                extension = direction * (anchor - level)
                if extension <= buffer or extension > settings["reclaim_max_extension_atr"] * atr:
                    reason = "entry_quote_outside_confirmation_band"
        if reason == "confirmed":
            signal[signal_index] = direction
        records.append({"setup_available_at": row.available_at, "direction": direction,
                        "level": level, "buffer": buffer, "setup_atr": atr,
                        "h1_available_at": h1.available_at.iloc[hi], "h1_close": h1.bid_close.iloc[hi],
                        "h1_ema": h1.ema.iloc[hi], "m15_ema": row.ema,
                        "signal_index": signal_index, "entry_index": entry_index, "reason": reason})
    return signal, pd.DataFrame(records)


def outcome_pool(bars, prepared, protocol, era, bounds):
    """All static-eligible BUY/SELL outcomes for the same fill model as signals."""
    times = pd.DatetimeIndex(bars.timestamp_utc)
    epochs = bars.epoch_seconds.to_numpy()
    config = protocol["execution"]
    start, end = map(pd.Timestamp, bounds)
    entries = np.arange(1, len(bars) - 1)
    exits = entries + 1
    days = times.normalize()
    holidays = {d: bool(excluded_holiday(d)) for d in days.unique()}
    bad_day = np.array([holidays[d] for d in days]) if config["holiday_exclusion"] else np.zeros(len(bars), bool)
    spread = (bars.ask_open - bars.bid_open).to_numpy()
    hour, minute = map(int, config["friday_no_entry_from_utc"].split(":"))
    friday_late = (times.weekday == 4) & (times.hour * 60 + times.minute >= hour * 60 + minute)
    allowed = (prepared["ready"][entries - 1] & (epochs[entries] - epochs[entries - 1] == 300)
               & (times[entries] >= start) & (times[exits] < end)
               & ~bad_day[entries] & ~friday_late[entries]
               & (spread[entries] >= 0) & (spread[entries] <= config["max_entry_spread"]))
    entries, exits = entries[allowed], exits[allowed]
    distance = config["stop_distance_price_units"]
    records = []
    for direction in (1, -1):
        side = "bid" if direction == 1 else "ask"
        anchor = bars[f"{side}_open"].to_numpy()[entries]
        price = bars["ask_open" if direction == 1 else "bid_open"].to_numpy()[entries]
        stop = anchor - direction * distance
        extreme = bars[f"{side}_{'low' if direction == 1 else 'high'}"].to_numpy()[entries]
        stopped = direction * (extreme - stop) <= 0
        next_price = bars[f"{side}_open"].to_numpy()[exits]
        exit_price = np.where(stopped, stop, next_price)
        gap = ~stopped & (epochs[exits] - epochs[entries] > 300)
        # A stop occurs inside its entry candle, hence on that candle's UTC day.
        # Keep its bar-open label (not a fabricated exact execution second).
        # The separate exit_index still enforces the declared conservative slot.
        exit_times = pd.to_datetime(np.where(stopped, epochs[entries], epochs[exits]), unit="s", utc=True)
        frame = pd.DataFrame({"era": era, "entry_index": entries, "exit_index": exits,
            "signal_index": entries - 1, "entry_ts": times[entries], "exit_ts": exit_times,
            "entry_day": epochs[entries] // 86400,
            "exit_day": exit_times.asi8 // (86400 * 10**9), "dir": "BUY" if direction == 1 else "SELL",
            "entry": price, "exit": exit_price, "stop": stop, "spread_paid": spread[entries],
            "r_multiple": direction * (exit_price - price) / distance,
            "pnl_usd": direction * (exit_price - price) * protocol["usd_per_price_unit"],
            "exit_reason": np.where(stopped, "stop", np.where(gap, "delayed_time_exit", "time_exit")),
            "exit_time_precision": np.where(stopped, "M5_bar_open_label", "observed_bar_open"),
            "exit_not_after_exclusive": pd.to_datetime(
                np.where(stopped, epochs[entries] + 300, epochs[exits] + 1), unit="s", utc=True),
            "flags": np.where(gap, "gap_risk", ""), "atr": prepared["atr"][entries - 1]})
        records.append(frame)
    return pd.concat(records, ignore_index=True)


def select_schedule(pool, signal, daily_halt_r):
    """Chronological one-position selection with realised UTC daily loss halt."""
    direction = np.where(pool.dir.eq("BUY"), 1, -1)
    candidates = pool.loc[signal[pool.signal_index.to_numpy()] == direction].sort_values("entry_index")
    selected, totals, last_exit = [], {}, -1
    for row in candidates.itertuples():
        if row.entry_index <= last_exit or totals.get(row.entry_day, 0.) <= daily_halt_r:
            continue
        selected.append(row.Index)
        last_exit = row.exit_index
        totals[row.exit_day] = totals.get(row.exit_day, 0.) + row.r_multiple
    return pool.loc[selected].copy(), selected
