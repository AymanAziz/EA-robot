"""Report declared execution sensitivities; never promote a better variant."""

import argparse
import csv
from dataclasses import replace
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .data import read_ticks
from .engine import Contract
from .replay import replay, TIMER_DTYPE


def diagnose(output):
    output = Path(output)
    native = output / "native"
    symbol = dict(csv.reader((native / "symbol.csv").open()))
    offset = int(symbol["offset_seconds"])
    ticks, _ = read_ticks(native / "all_ticks.bin", server_offset=offset)
    timers = np.fromfile(native / "timers.bin", TIMER_DTYPE)
    base = Contract(
        tick=float(symbol["tick_size"]),
        stops=float(symbol["stops_level"]) * float(symbol["point"]),
        freeze=float(symbol["freeze_level"]) * float(symbol["point"]),
        leverage=float(symbol["leverage"]),
    )
    scenarios = [
        ("declared_conservative_USC", base, 1.0),
        ("no_profit_protection_ablation", replace(base, protection_enabled=False), 1.0),
        ("spread_1_5", base, 1.5),
        ("spread_2_0", base, 2.0),
        ("extra_round_trip_cost_0_2_USC", replace(base, round_trip_cost=0.2), 1.0),
        ("extra_round_trip_cost_0_5_USC", replace(base, round_trip_cost=0.5), 1.0),
        ("native_favourable_target_fill", replace(base, target_fill="quote"), 1.0),
        ("native_coarse_money_precision", replace(base, target_fill="quote", money_quantum=1.0), 1.0),
    ]
    destination = output / "diagnostics"
    destination.mkdir(exist_ok=True)
    (destination / "PLAN.json").write_text(
        json.dumps(
            {
                "scenarios": [n for n, _, _ in scenarios],
                "decision_changed": False,
                "use": "engineering stress diagnostics only; generated ticks, one month, not four-era Step5",
                "cost_timing": "extra total round-trip cost reserved at entry and debited at close; not a verified broker commission schedule",
                "precision": "USC scenarios use 0.01 USC rounding; native coarse precision uses 1 USC rounding",
            },
            indent=2,
        )
        + "\n"
    )
    rows = []
    for name, contract, spread_factor in scenarios:
        q, tm = ticks, timers
        if spread_factor != 1:
            q, tm = ticks.copy(), timers.copy()
            for data in (q, tm):
                data["ask"] = data["bid"] + (data["ask"] - data["bid"]) * spread_factor
        result = replay(q, tm, contract, offset=offset)
        trades = pd.DataFrame(result["trades"])
        trades.to_csv(destination / f"{name}_trades.csv", index=False)
        if len(trades):
            values = trades.pnl_usc.to_numpy()
            equity = np.r_[contract.initial_equity, contract.initial_equity + values.cumsum()]
            row = dict(
                scenario=name,
                trades=len(trades),
                buy=int(trades.side.eq(1).sum()),
                sell=int(trades.side.eq(-1).sum()),
                pnl_usc=float(values.sum()),
                mean_r=float(trades.r_multiple.mean()),
                win_rate=float(trades.pnl_usc.gt(0).mean()),
                max_closed_trade_drawdown_usc=float((np.maximum.accumulate(equity) - equity).max()),
                profit_floor_exits=int(trades.exit_reason.eq("profit_floor").sum()),
                target_exits=int(trades.exit_reason.eq("tp").sum()),
                profitable_stop_exits=int((trades.exit_reason.eq("sl") & trades.pnl_usc.gt(0)).sum()),
            )
        else:
            row = dict(scenario=name, trades=0, pnl_usc=0.0, mean_r=None, win_rate=None)
        rows.append(row)
        pd.DataFrame(rows).to_csv(destination / "RESULT.csv", index=False)
        print(json.dumps(row), flush=True)
    (destination / "RESULT.json").write_text(
        json.dumps(
            {
                "scenarios": rows,
                "formal_step5_passed": False,
                "not_evaluated": [
                    "full-era execution-delay returns",
                    "qualified tick gaps",
                    "same-bar path ambiguity across four eras",
                ],
                "qualification": "NOT EVALUATED; these are generated-path diagnostics, not statistical qualification or a matched random baseline",
            },
            indent=2,
        )
        + "\n"
    )
    return rows


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    diagnose(parser.parse_args().output)
