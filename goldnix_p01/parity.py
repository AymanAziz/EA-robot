"""Actual strategy deal and signal comparison, with no native decisions as inputs."""

import argparse
import csv
from dataclasses import asdict
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .data import read_ticks
from .engine import Contract
from .replay import replay, TIMER_DTYPE


def compare(native, reference):
    columns = ["entry_utc", "exit_utc", "side", "entry", "exit", "exit_reason"]
    left, right = native.reindex(columns=columns).copy(), reference.reindex(columns=columns).copy()
    for frame in (left, right):
        for key in ("entry", "exit"):
            frame[key + "_bar"] = frame[key + "_utc"] // 60
        if frame.duplicated(["entry_bar", "side"]).any():
            raise ValueError("Duplicate trade key")
    joined = left.merge(
        right,
        on=["entry_bar", "side"],
        how="outer",
        suffixes=("_native", "_python"),
        indicator=True,
        validate="one_to_one",
    )
    match = joined["_merge"].eq("both")
    for key in ("exit_bar", "exit_reason"):
        match &= joined[key + "_native"].eq(joined[key + "_python"])
    for key in ("entry", "exit"):
        match &= abs(joined[key + "_native"] - joined[key + "_python"]).le(1e-8)
    # Stricter than the required M1 bar check: exact entry and whole exit second.
    match &= joined.entry_utc_native.eq(joined.entry_utc_python)
    match &= np.floor(joined.exit_utc_native).eq(np.floor(joined.exit_utc_python))
    joined["match"] = match
    ratio = float(match.mean()) if len(joined) else None
    return dict(
        status="INSUFFICIENT_DATA" if ratio is None else "PASS" if ratio >= 0.95 else "FAIL",
        native_trades=len(left),
        python_trades=len(right),
        comparison_rows=len(joined),
        matching_trades=int(match.sum()),
        match_ratio=ratio,
    ), joined


def analyse(output):
    output = Path(output)
    native = output / "native"
    receipt = dict(csv.reader((native / "receipt.csv").open()))
    if (
        receipt.get("completed") != "1"
        or receipt.get("tester") != "1"
        or receipt.get("audit_halt") != "false"
        or receipt.get("state_broken") != "false"
    ):
        raise ValueError("A completed, nonhalted native tester run is required")
    symbol = dict(csv.reader((native / "symbol.csv").open()))
    offset = int(symbol["offset_seconds"])
    ticks, data_audit = read_ticks(native / "all_ticks.bin", server_offset=offset)
    timer_path = native / "timers.bin"
    if timer_path.stat().st_size % TIMER_DTYPE.itemsize:
        raise ValueError("Truncated timer records")
    timers = np.fromfile(timer_path, TIMER_DTYPE)
    if len(ticks) != int(receipt["ticks"]) or len(timers) != int(receipt["timers"]):
        raise ValueError("Exported event counts differ from native receipt")
    contract = Contract(
        tick=float(symbol["tick_size"]),
        stops=float(symbol["stops_level"]) * float(symbol["point"]),
        freeze=float(symbol["freeze_level"]) * float(symbol["point"]),
        initial_equity=float(symbol["initial_equity_usc"]),
        money_quantum=1.0,
        leverage=float(symbol["leverage"]),
        target_fill="quote",
    )
    reference = replay(ticks, timers, contract, offset=offset)
    runs = list((native / "runs").iterdir())
    if len(runs) != 1:
        raise ValueError("Ambiguous native strategy trace")
    run = runs[0]
    deals = pd.read_csv(native / "broker_deals.csv")
    if abs(deals[["commission_usc", "swap_usc", "fee_usc"]].to_numpy()).sum() > 1e-8:
        raise ValueError("Nonzero charges require an independent historical cost model before comparison")
    actual = pd.read_csv(run / "trades.csv")
    events = pd.read_csv(run / "events.csv")
    actual["side"] = actual.dir.map({"BUY": 1, "SELL": -1})
    exits = deals[deals.side == 1]
    actual = actual.merge(exits[["position", "reason"]], on="position", validate="one_to_one")
    actual["exit_reason"] = actual.reason.map({4: "sl", 5: "tp", 3: "session_close"})
    floor_times = set(
        events.loc[
            events.event.eq("PROFIT_PROTECTION") & events.details.str.contains("profit_floor_exit_confirmed"),
            "utc_epoch",
        ]
    )
    actual.loc[actual.reason.eq(3) & actual.exit_utc.isin(floor_times), "exit_reason"] = "profit_floor"
    censor_times = set(events.loc[events.event.eq("REPLAY_END_CLOSE"), "utc_epoch"])
    actual.loc[actual.exit_utc.isin(censor_times), "exit_reason"] = "censored_boundary"
    expected = pd.DataFrame(reference["trades"])
    parity, compared = compare(actual, expected)
    actual.to_csv(output / "native_trades.csv", index=False)
    expected.to_csv(output / "reference_trades.csv", index=False)
    compared.to_csv(output / "trade_comparison.csv", index=False)
    compared.loc[~compared.match].to_csv(output / "mismatches.csv", index=False)
    signals = pd.read_csv(run / "signals.csv")
    signals = signals[signals.context.eq("new_m1")]
    signals = signals.merge(
        pd.DataFrame(reference["decisions"]),
        on="signal_utc",
        how="outer",
        suffixes=("_native", "_python"),
        indicator=True,
        validate="one_to_one",
    )
    signals["match"] = (
        signals["_merge"].eq("both")
        & signals.reason_native.eq(signals.reason_python)
        & signals.direction_native.eq(signals.direction_python)
    )
    signals["atr_error"] = abs(signals.atr_native - signals.atr_python)
    signals["match"] &= signals.atr_error.le(1e-8)
    signals.to_csv(output / "signal_comparison.csv", index=False)
    native_ready = events.loc[events.event.eq("READY"), "utc_epoch"].tolist()
    result = dict(
        trade_parity=parity,
        signal_rows=len(signals),
        matching_signals=int(signals.match.sum()),
        max_atr_error=float(signals.atr_error.max()) if len(signals) else None,
        readiness_exact=native_ready == reference["readiness"],
        buy_trades=int(actual.side.eq(1).sum()),
        sell_trades=int(actual.side.eq(-1).sum()),
        contract=asdict(contract),
        data=data_audit,
        native_pnl_usc=float(actual.pnl_usc.sum()),
        formal_step8_passed=False,
        formal_reason="Steps6 and7 have not passed; generated broker ticks and USD cent rounding are engineering evidence only",
        accounting_limit="Tester rounds USD to 0.01 = 1 USC; actual USC account has finer precision. Contract explicitly mirrors tester, not real-cent settlement.",
        source_sha256={
            p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in Path(__file__).parent.glob("*.py")
        },
        timers_sha256=hashlib.sha256(timer_path.read_bytes()).hexdigest(),
    )
    result["engineering_passed"] = (
        parity["status"] == "PASS"
        and len(signals) > 0
        and bool(signals.match.all())
        and result["readiness_exact"]
    )
    (output / "PARITY.json").write_text(json.dumps(result, indent=2) + "\n")
    print(
        json.dumps({k: v for k, v in result.items() if k not in ("data", "contract", "source_sha256")}),
        flush=True,
    )
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    analyse(parser.parse_args().output)
