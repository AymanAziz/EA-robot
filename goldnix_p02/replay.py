"""Causal M1 strategy replay on an observed quote and timer stream.

Only external quote/clock/session inputs are consumed from MT5. Native readiness,
signal directions, decisions, entry lists and exits are never replay inputs.
"""

from datetime import UTC, datetime

import numpy as np

from ingest.holidays import excluded_holiday
from goldnix_p01.data import features, minute_bars, validate_ticks
from goldnix_p01.engine import Broker, grid
from .features import filter_features

TIMER_DTYPE = np.dtype(
    [("utc", "<i8"), ("quote_ms", "<i8"), ("bid", "<f8"), ("ask", "<f8"), ("end", "<i8"), ("flags", "<i8")]
)


def replay(ticks, timers, contract, *, offset=7200, candidate="P01", history_bars=None):
    validate_ticks(ticks)
    if len(timers) == 0 or timers.dtype != TIMER_DTYPE or np.any(np.diff(timers["utc"]) < 0):
        raise ValueError("Chronological nonempty timer stream required")
    quote_ms = timers["quote_ms"] - offset * 1000
    if np.any(quote_ms // 1000 > timers["utc"]):
        raise ValueError("Timer cannot observe a future quote")
    if (
        np.any(np.diff(quote_ms) < 0)
        or not np.isfinite(timers["bid"]).all()
        or not np.isfinite(timers["ask"]).all()
        or np.any(timers["bid"] <= 0)
        or np.any(timers["ask"] < timers["bid"])
    ):
        raise ValueError("Invalid timer quote chronology or prices")
    bars = filter_features(features(minute_bars(ticks)), candidate, history=history_bars)
    opens = bars.epoch_seconds.to_numpy()
    stat = bars[["direction", "atr", "distance", "spread"]].to_numpy()
    # These schedules describe availability, not native decisions or outcomes.
    quote_end = np.searchsorted(ticks["utc_ms"], quote_ms, side="right")
    current_minutes = quote_ms // 60000 * 60
    completed_counts = np.searchsorted(opens, current_minutes, side="left")
    broker = Broker(contract)
    decisions, readiness = [], []
    tick_cursor = closed_count = attempts = 0
    last_exit_bar = last_signal = 0
    day = (int(timers["utc"][0]) + 28800) // 86400
    base_equity = broker.balance
    realized_r = 0.0
    daily_halt = False
    ready = False
    warm_count = 0
    warm_last = current_bar = -1
    previous_timer = 0
    stable_since = int(timers["utc"][0])
    holiday_cache = {}
    for i in range(len(timers)):
        now, _, bid, ask, market_end, _ = timers[i]
        now, market_end = int(now), int(market_end)
        for j in range(tick_cursor, int(quote_end[i])):
            broker.quote(int(ticks["utc_ms"][j]), bid=float(ticks["bid"][j]), ask=float(ticks["ask"][j]))
        tick_cursor = int(quote_end[i])
        paused = previous_timer > 0 and (now - previous_timer > 10 or now < previous_timer)
        previous_timer = now
        if paused:
            ready = False
            warm_count = 0
            stable_since = now
            if broker.position:
                broker.close(now, bid if broker.position["side"] == 1 else ask, "recovery")
            continue
        equity = broker.equity(bid, ask)
        if base_equity - equity >= 10:
            daily_halt = True
        utc_day = now // 86400
        weekday = (utc_day + 3) % 7  # Monday=0
        hour = now % 86400 // 3600
        if broker.position and (
            daily_halt or (market_end > 0 and now >= market_end - 120) or (weekday == 4 and hour >= 20)
        ):
            why = "daily_loss" if daily_halt else "session_close"
            broker.close(now, bid if broker.position["side"] == 1 else ask, why)
        while closed_count < len(broker.trades):
            trade = broker.trades[closed_count]
            realized_r += trade["r_multiple"]
            last_exit_bar = int(trade["exit_utc"]) // 60 * 60
            closed_count += 1
        if abs(now - int(quote_ms[i]) // 1000) <= 3:
            broker.protect(now, bid=bid, ask=ask)
        next_day = (now + 28800) // 86400
        if next_day > day and broker.position is None and closed_count == len(broker.trades):
            day, attempts, base_equity, realized_r, daily_halt = next_day, 0, broker.balance, 0.0, False
        if now - stable_since < 5:
            continue
        current = int(current_minutes[i])
        count = int(completed_counts[i])
        if not ready:
            if count < 100:
                continue
            if warm_count == 0:
                warm_last = int(opens[count - 1])
            warm_count += 5
            if warm_count < 100:
                continue
            warm_count = 0
            if warm_last != int(opens[count - 1]):
                continue
            ready = True
            current_bar = current
            last_signal = max(last_signal, warm_last)
            readiness.append(now)
            continue  # Startup evaluation can report a signal but never enter.
        if current <= current_bar:
            continue
        if current - current_bar != 60 or count == 0 or opens[count - 1] != current_bar:
            ready = False
            warm_count = 0
            continue
        signal = current_bar
        current_bar = current
        if signal <= last_signal:
            continue
        last_signal = signal
        side, atr, distance, spread = stat[count - 1]
        side = int(side)
        reason = "eligible"
        if daily_halt or base_equity - broker.equity(bid, ask) >= 10:
            reason = "daily_loss_limit"
        elif realized_r <= -2:
            reason = "daily_r_limit"
        elif attempts >= 7:
            reason = "daily_attempt_limit"
        elif next_day != day:
            reason = "clock_risk_day_mismatch"
        elif side == 0:
            reason = "no_breakout"
        elif distance + spread > 5:
            reason = "risk_cap"
        elif spread > 0.30 * atr:
            reason = "spread"
        elif weekday == 4 and hour >= 19:
            reason = "friday"
        else:
            signal_day = signal // 86400
            if signal_day not in holiday_cache:
                holiday_cache[signal_day] = excluded_holiday(datetime.fromtimestamp(signal, UTC))
            if holiday_cache[signal_day]:
                reason = "holiday"
            elif broker.position is not None or closed_count < len(broker.trades):
                reason = "position_or_order_open"
            elif now // 60 * 60 <= last_exit_bar:
                reason = "exit_bar"
            elif market_end == 0 or now >= market_end - 120:
                reason = "market_closed_or_buffer"
            elif abs(now - int(quote_ms[i]) // 1000) > 3 or ask < bid:
                reason = "stale_quote"
            elif not signal + 60 <= now < signal + 70:
                reason = "startup_resync_or_stale_bar"
        if reason == "eligible":
            anchor, entry = (bid, ask) if side == 1 else (ask, bid)
            stop = grid(anchor - side * distance, contract.tick)
            risk = side * (entry - stop) * contract.exposure_usc_per_price
            if risk <= 0 or risk > 5.000001:
                reason = "actual_risk_cap"
            elif entry * contract.exposure_usc_per_price / contract.leverage > broker.equity(bid, ask):
                reason = "margin"
            elif abs(anchor - stop) < contract.stops:
                reason = "broker_stop_distance"
        decisions.append(
            dict(
                decision_utc=now,
                signal_utc=signal,
                direction=side,
                atr=atr,
                distance=distance,
                spread=spread,
                reason=reason,
                daily_r=realized_r,
                attempts=attempts,
                bid=bid,
                ask=ask,
            )
        )
        if reason == "eligible":
            attempts += 1
            broker.open(side=side, utc=now, bid=bid, ask=ask, distance=distance, atr=atr)
    # The exporter forces a close at the test boundary; label it as censoring.
    if broker.position:
        broker.close(
            int(timers["utc"][-1]),
            float(timers["bid"][-1]) if broker.position["side"] == 1 else float(timers["ask"][-1]),
            "censored_boundary",
        )
    return dict(
        trades=broker.trades,
        decisions=decisions,
        readiness=readiness,
        modifications=broker.updates,
        balance_usc=broker.balance,
        limitation="No swap or rejected fills unless explicit in the supplied contract; native replay is engineering evidence only",
    )
