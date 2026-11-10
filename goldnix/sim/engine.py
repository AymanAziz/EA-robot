"""H1 bar-by-bar trade simulation."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from ingest.holidays import excluded_holiday
from params.atr import atr_simple
from signals.aroon import aroon_osc_series
from signals.crosses import cross_series
from sim.policy import ExitDecision, bar_excursions, resolve_exit

TRADE_COLUMNS = [
    "era",
    "entry_ts",
    "exit_ts",
    "dir",
    "layers",
    "entry",
    "exit",
    "stop",
    "target",
    "atr",
    "spread_paid",
    "r_multiple",
    "mae_r",
    "mfe_r",
    "exit_reason",
    "flags",
]


@dataclass(frozen=True)
class SimulationResult:
    trades: pd.DataFrame
    signals: int
    skipped_by_vol_ceiling: int


def _minutes(value: str) -> int:
    hour, minute = (int(part) for part in value.split(":"))
    return hour * 60 + minute


def prepare_bars(
    bars: pd.DataFrame,
    config: dict,
    *,
    atr_period: int = 14,
) -> pd.DataFrame:
    """Add closed-bar Aroon crossing signals and parity-selected simple ATR."""
    prepared = bars.copy()
    mid_high = (prepared["bid_high"] + prepared["ask_high"]) / 2
    mid_low = (prepared["bid_low"] + prepared["ask_low"]) / 2
    mid_close = (prepared["bid_close"] + prepared["ask_close"]) / 2
    oscillator = aroon_osc_series(
        mid_high.to_numpy(),
        mid_low.to_numpy(),
        period=int(config["aroon_period"]),
        ties=config["ties"],
    )
    prepared["signal"] = cross_series(oscillator, float(config["threshold"]))
    prepared["atr"] = atr_simple(
        mid_high.to_numpy(),
        mid_low.to_numpy(),
        mid_close.to_numpy(),
        period=atr_period,
    )
    return prepared


def run_engine(
    bars: pd.DataFrame,
    config: dict,
    *,
    gaps: pd.DataFrame | None = None,
    atr_period: int = 14,
) -> SimulationResult:
    """Simulate closed-bar signals with fills at the following H1 open."""
    if "signal" not in bars or "atr" not in bars:
        bars = prepare_bars(bars, config, atr_period=atr_period)
    records = []
    signals = int(bars["signal"].isin([-1, 1]).sum())
    skipped_by_vol_ceiling = 0
    realised_r_by_day: dict[object, float] = {}
    index = 1
    while index < len(bars):
        signal_bar = bars.iloc[index - 1]
        if signal_bar["signal"] not in (-1, 1):
            index += 1
            continue
        entry_bar = bars.iloc[index]
        entry_day = entry_bar["timestamp_utc"].date()
        if realised_r_by_day.get(entry_day, 0.0) <= float(config["daily_halt_r"]):
            index += 1
            continue
        entry_timestamp = entry_bar["timestamp_utc"]
        if (
            entry_timestamp.weekday() == 4
            and entry_timestamp.hour * 60 + entry_timestamp.minute
            >= _minutes(config["friday_no_entry_from_utc"])
        ):
            index += 1
            continue
        if config["holiday_exclusion"] and excluded_holiday(signal_bar["timestamp_utc"]):
            index += 1
            continue
        signal_atr = float(signal_bar["atr"])
        ceiling_spread = float(signal_bar["ask_close"] - signal_bar["bid_close"])
        if ceiling_spread > float(config["vol_ceiling_atr"]) * signal_atr:
            skipped_by_vol_ceiling += 1
            index += 1
            continue
        atr = signal_atr
        distance = max(float(config["stop_atr"]) * atr, float(config["min_distance_usd"]))
        reward_distance = distance * float(config["target_atr"]) / float(config["stop_atr"])
        is_buy = signal_bar["signal"] == 1
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

        mae_r = 0.0
        mfe_r = 0.0
        for exit_index in range(index, len(bars)):
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
            bar_mae_r, bar_mfe_r = bar_excursions(
                bar,
                is_buy=is_buy,
                entry=entry,
                distance=distance,
                exit_at_open=decision.at_open if decision is not None else False,
            )
            mae_r = min(mae_r, bar_mae_r)
            mfe_r = max(mfe_r, bar_mfe_r)
            if decision is None:
                if exit_index != len(bars) - 1:
                    continue
                decision = ExitDecision(
                    float(bar["bid_close"] if is_buy else bar["ask_close"]),
                    "end_of_data",
                    False,
                )
            exit_price = decision.price
            exit_reason = decision.reason
            r_multiple = (
                (exit_price - entry) / distance
                if is_buy
                else (entry - exit_price) / distance
            )
            flags = ""
            if gaps is not None and not gaps.empty:
                open_across_gap = (
                    (gaps["gap_start"] >= entry_bar["timestamp_utc"])
                    & (gaps["gap_end"] <= bar["timestamp_utc"])
                ).any()
                if open_across_gap:
                    flags = "gap_risk"
            records.append(
                {
                    "era": entry_bar["era"],
                    "entry_ts": entry_bar["timestamp_utc"],
                    "exit_ts": bar["timestamp_utc"],
                    "dir": "BUY" if is_buy else "SELL",
                    "layers": 1,
                    "entry": entry,
                    "exit": exit_price,
                    "stop": stop,
                    "target": target,
                    "atr": atr,
                    "spread_paid": spread,
                    "r_multiple": r_multiple,
                    "mae_r": mae_r,
                    "mfe_r": mfe_r,
                    "exit_reason": exit_reason,
                    "flags": flags,
                }
            )
            exit_day = bar["timestamp_utc"].date()
            realised_r_by_day[exit_day] = (
                realised_r_by_day.get(exit_day, 0.0) + r_multiple
            )
            index = exit_index
            break
        index += 1

    return SimulationResult(
        trades=pd.DataFrame.from_records(records, columns=TRADE_COLUMNS),
        signals=signals,
        skipped_by_vol_ceiling=skipped_by_vol_ceiling,
    )
