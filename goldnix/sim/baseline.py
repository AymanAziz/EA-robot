"""Uniform random-entry baseline for separating signal edge from price drift."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from ingest.holidays import excluded_holiday
from sim.policy import ExitDecision, resolve_exit


@dataclass(frozen=True)
class BaselineResult:
    trades: pd.DataFrame
    draws: pd.DataFrame
    eligible_bars: int


def _minutes(value: str) -> int:
    hour, minute = (int(part) for part in value.split(":"))
    return hour * 60 + minute


def eligible_signal_indices(bars: pd.DataFrame, config: dict) -> np.ndarray:
    """Return signal-bar indices passing every static decision-config filter."""
    eligible = []
    for index in range(len(bars) - 1):
        signal_bar = bars.iloc[index]
        entry_bar = bars.iloc[index + 1]
        atr = float(signal_bar["atr"])
        if not np.isfinite(atr) or atr <= 0:
            continue
        entry_timestamp = entry_bar["timestamp_utc"]
        if (
            entry_timestamp.weekday() == 4
            and entry_timestamp.hour * 60 + entry_timestamp.minute
            >= _minutes(config["friday_no_entry_from_utc"])
        ):
            continue
        if config["holiday_exclusion"] and excluded_holiday(signal_bar["timestamp_utc"]):
            continue
        spread = float(signal_bar["ask_close"] - signal_bar["bid_close"])
        if spread > float(config["vol_ceiling_atr"]) * atr:
            continue
        eligible.append(index)
    return np.asarray(eligible, dtype=int)


def _simulate_entry(
    bars: pd.DataFrame,
    config: dict,
    signal_index: int,
    direction: int,
) -> dict:
    signal_bar = bars.iloc[signal_index]
    entry_index = signal_index + 1
    entry_bar = bars.iloc[entry_index]
    atr = float(signal_bar["atr"])
    distance = max(float(config["stop_atr"]) * atr, float(config["min_distance_usd"]))
    reward_distance = distance * float(config["target_atr"]) / float(config["stop_atr"])
    is_buy = direction == 1
    if is_buy:
        entry = float(entry_bar["ask_open"])
        anchor = float(entry_bar["bid_open"])
        stop = anchor - distance
        target = anchor + reward_distance
        spread = entry - anchor
    else:
        entry = float(entry_bar["bid_open"])
        anchor = float(entry_bar["ask_open"])
        stop = anchor + distance
        target = anchor - reward_distance
        spread = anchor - entry

    decision = None
    exit_bar = None
    for exit_index in range(entry_index, len(bars)):
        bar = bars.iloc[exit_index]
        timestamp = bar["timestamp_utc"]
        friday_flat = (
            timestamp.weekday() == 4
            and timestamp.hour * 60 + timestamp.minute
            >= _minutes(config["friday_flat_utc"])
        )
        decision = resolve_exit(
            bar,
            is_buy=is_buy,
            stop=stop,
            target=target,
            fill_policy=config["fill_policy"],
            gap_policy=config["gap_policy"],
            friday_flat=friday_flat,
        )
        exit_bar = bar
        if decision is not None:
            break
    if decision is None:
        decision = ExitDecision(
            float(exit_bar["bid_close"] if is_buy else exit_bar["ask_close"]),
            "end_of_data",
            False,
        )
    r_multiple = (
        (decision.price - entry) / distance
        if is_buy
        else (entry - decision.price) / distance
    )
    return {
        "signal_index": signal_index,
        "entry_ts": entry_bar["timestamp_utc"],
        "exit_ts": exit_bar["timestamp_utc"],
        "dir": "BUY" if is_buy else "SELL",
        "entry": entry,
        "exit": decision.price,
        "stop": stop,
        "target": target,
        "atr": atr,
        "distance": distance,
        "spread_paid": spread,
        "r_multiple": r_multiple,
        "exit_reason": decision.reason,
    }


def run_random_baseline(
    bars: pd.DataFrame,
    config: dict,
    *,
    longs: int,
    shorts: int,
    draws: int = 200,
    seed: int,
) -> BaselineResult:
    """Run reproducible uniform random entries with a fixed direction split."""
    candidates = eligible_signal_indices(bars, config)
    baskets = longs + shorts
    if baskets > len(candidates):
        raise ValueError(
            f"requested {baskets} baskets from only {len(candidates)} eligible bars"
        )
    rng = np.random.default_rng(seed)
    trade_records = []
    draw_records = []
    for draw in range(draws):
        selected = rng.choice(candidates, size=baskets, replace=False)
        directions = np.asarray([1] * longs + [-1] * shorts, dtype=np.int8)
        rng.shuffle(directions)
        draw_trades = []
        for signal_index, direction in zip(selected, directions):
            trade = _simulate_entry(bars, config, int(signal_index), int(direction))
            trade["draw"] = draw
            draw_trades.append(trade)
            trade_records.append(trade)
        frame = pd.DataFrame(draw_trades)
        draw_records.append(
            {
                "draw": draw,
                "baskets": len(frame),
                "win_rate": float((frame["r_multiple"] > 0).mean()),
                "mean_r": float(frame["r_multiple"].mean()),
                "long_mean_r": float(
                    frame.loc[frame["dir"] == "BUY", "r_multiple"].mean()
                ),
                "short_mean_r": float(
                    frame.loc[frame["dir"] == "SELL", "r_multiple"].mean()
                ),
            }
        )
    return BaselineResult(
        trades=pd.DataFrame(trade_records),
        draws=pd.DataFrame(draw_records),
        eligible_bars=len(candidates),
    )
