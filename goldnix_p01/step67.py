"""Updated P01 Step6 diagnostic and Step7 prerequisite audit.

This entry point cannot issue a qualifying freeze or read holdout prices.
"""

import argparse
import csv
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
import hashlib
import json
from pathlib import Path
import shutil

import numpy as np
import pandas as pd

from params.config import load_yaml
from .data import read_ticks
from .engine import Contract
from .replay import TIMER_DTYPE, replay
from .statistics import monthly_bootstrap, chunked_drawdown

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    with Path(path).open("x") as handle:
        json.dump(value, handle, indent=2, allow_nan=False)
        handle.write("\n")


def candidate_sources():
    paths = [
        ROOT / "goldnix_auto_m1" / name
        for name in (
            "GoldnixAutoM1.mq5",
            "AutoM1Policy.mqh",
            "ProfitPolicy.mqh",
            "ProfitJournal.mqh",
            "ProfitManager.mqh",
            "protection_protocol.json",
        )
    ]
    paths += [HERE / name for name in ("data.py", "policy.py", "engine.py", "replay.py")]
    return {str(p.relative_to(ROOT)): sha(p) for p in paths}


def holdout_preflight(step6, *, current_source, freeze_verified, holdout_window, consumed_windows):
    blockers = []
    if step6.get("candidate") != "M1_PROFIT_PROTECTION_P01":
        blockers.append("wrong_candidate")
    if step6.get("formal_qualified") is not True:
        blockers.append("step6_not_qualified")
    gates = step6.get("gates", {})
    if set(gates) != {f"G{i}" for i in range(1, 10)} or not all(
        g.get("formal_passed") is True for g in gates.values()
    ):
        blockers.append("nine_formal_gates_not_passed")
    if not current_source or step6.get("source_sha256") != current_source:
        blockers.append("candidate_source_changed_or_missing")
    if not freeze_verified:
        blockers.append("matching_qualified_freeze_missing")
    if holdout_window is None:
        blockers.append("untouched_period_not_registered")
    else:
        start, end = [datetime.fromisoformat(s.replace("Z", "+00:00")) for s in holdout_window]
        if start.tzinfo is None or end.tzinfo is None or start >= end:
            raise ValueError("A positive timezone-aware holdout interval is required")
        for old_start, old_end in consumed_windows:
            a, b = [datetime.fromisoformat(s.replace("Z", "+00:00")) for s in (old_start, old_end)]
            if start < b and a < end:
                blockers.append("holdout_period_already_consumed")
                break
    return dict(
        status="BLOCKED_PREREQUISITES" if blockers else "PREFLIGHT_READY_NOT_EVALUATED",
        blockers=blockers,
        formal_passed=False,
        holdout_payload_read=False,
        holdout_attempt_created=False,
        requested_window=holdout_window,
        note="Preflight only. This function never reads or consumes holdout price data.",
    )


def run():
    plan = json.loads((HERE / "step67_protocol.json").read_text())
    run_id = datetime.now(UTC).strftime("P01S67_%Y%m%dT%H%M%SZ")
    output = HERE / "step67" / "out" / run_id
    output.mkdir(parents=True, exist_ok=False)
    sources = candidate_sources()
    write(
        output / "PLAN.json", plan | {"started_utc": datetime.now(UTC).isoformat(), "source_sha256": sources}
    )
    source_dir = output / "SOURCE"
    for relative in sources:
        target = source_dir / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, target)
    for name in ("statistics.py", "step67.py", "step67_protocol.json"):
        shutil.copy2(HERE / name, source_dir / name)
    rules = load_yaml(ROOT / plan["gates_path"])
    shutil.copy2(ROOT / plan["gates_path"], output / "rules.yaml")
    frames, windows = [], []
    for name in plan["engineering_runs"]:
        folder = HERE / "out" / name
        native = folder / "native"
        parity = json.loads((folder / "PARITY.json").read_text())
        adapter = json.loads((folder / "ADAPTER_MANIFEST.json").read_text())
        if (
            not parity["engineering_passed"]
            or adapter["production_source_sha256"] != sources["goldnix_auto_m1/GoldnixAutoM1.mq5"]
        ):
            raise ValueError("Native evidence does not bind the current P01 source")
        for header in ("AutoM1Policy.mqh", "ProfitPolicy.mqh", "ProfitJournal.mqh", "ProfitManager.mqh"):
            if sha(folder / "SOURCE" / header) != sources["goldnix_auto_m1/" + header]:
                raise ValueError("Native header differs from current candidate: " + header)
        for module in ("data.py", "engine.py", "policy.py", "replay.py"):
            if parity["source_sha256"][module] != sources["goldnix_p01/" + module]:
                raise ValueError("Replay changed since parity: " + module)
        symbol = dict(csv.reader((native / "symbol.csv").open()))
        offset = int(symbol["offset_seconds"])
        ticks, audit = read_ticks(native / "all_ticks.bin", server_offset=offset)
        if (
            audit["sha256"] != parity["data"]["sha256"]
            or sha(native / "timers.bin") != parity["timers_sha256"]
        ):
            raise ValueError("Native quote/timer input hash mismatch")
        timer_path = native / "timers.bin"
        if timer_path.stat().st_size % TIMER_DTYPE.itemsize:
            raise ValueError("Truncated timer file")
        timers = np.fromfile(timer_path, TIMER_DTYPE)
        deals = pd.read_csv(native / "broker_deals.csv")
        if abs(deals[["commission_usc", "swap_usc", "fee_usc"]].to_numpy()).sum() > 1e-8:
            raise ValueError("Nonzero historical charges require a qualified independent cost model")
        contract = Contract(
            tick=float(symbol["tick_size"]),
            stops=float(symbol["stops_level"]) * float(symbol["point"]),
            freeze=float(symbol["freeze_level"]) * float(symbol["point"]),
            leverage=float(symbol["leverage"]),
            money_quantum=plan["money_precision_usc"],
        )
        result = replay(ticks, timers, contract, offset=offset)
        trades = pd.DataFrame(result["trades"])
        trades["window"] = name
        trades["exit_ts"] = pd.to_datetime(trades.exit_utc, unit="s", utc=True)
        trades["entry_ts"] = pd.to_datetime(trades.entry_utc, unit="s", utc=True)
        if trades.exit_reason.eq("censored_boundary").any():
            raise ValueError("Censored trade cannot silently enter these return estimates")
        trades.to_csv(output / f"{name}_trades.csv", index=False)
        frames.append(trades)
        started = json.loads((folder / "STARTED.json").read_text())
        start = datetime.strptime(started["start"], "%Y.%m.%d").replace(tzinfo=UTC) - timedelta(
            seconds=offset
        )
        end = datetime.strptime(started["end_exclusive"], "%Y.%m.%d").replace(tzinfo=UTC) - timedelta(
            seconds=offset
        )
        window = dict(
            run=name,
            start_utc=start.isoformat(),
            end_exclusive_utc=end.isoformat(),
            duration_days=(end - start).total_seconds() / 86400,
            trades=len(trades),
            mean_r=float(trades.r_multiple.mean()),
            pnl_usc=float(trades.pnl_usc.sum()),
            buy=int(trades.side.eq(1).sum()),
            sell=int(trades.side.eq(-1).sum()),
            contract=asdict(contract),
            native_parity_receipt_sha256=sha(folder / "PARITY.json"),
            tick_sha256=audit["sha256"],
            timer_sha256=parity["timers_sha256"],
        )
        windows.append(window)
        print(json.dumps({"diagnostic_window": window}), flush=True)
        del ticks, timers, result
    trades = pd.concat(frames, ignore_index=True).sort_values("entry_utc").reset_index(drop=True)
    for previous, following in zip(windows, windows[1:]):
        if pd.Timestamp(previous["end_exclusive_utc"]) > pd.Timestamp(following["start_utc"]):
            raise ValueError("Overlapping windows cannot be pooled")
    if trades.duplicated(["entry_utc", "side"]).any():
        raise ValueError("Duplicate pooled trades")
    trades.to_csv(output / "trades.csv", index=False)
    bootstrap = monthly_bootstrap(
        trades.r_multiple,
        trades.exit_ts.dt.strftime("%Y-%m"),
        calendar=plan["bootstrap_months"],
        resamples=plan["bootstrap_resamples"],
        seed=plan["bootstrap_seed"],
    )
    observed_days = sum(w["duration_days"] for w in windows)
    annual_rate = len(trades) * 365.2425 / observed_days
    mc = chunked_drawdown(
        trades.pnl_usc.to_numpy() / 100,
        trades_per_year=max(1, round(annual_rate)),
        simulations=plan["monte_carlo_paths"],
        seed=plan["monte_carlo_seed"],
    )
    mc.update(
        observed_days=observed_days,
        observed_trades_per_year=annual_rate,
        account_usd=plan["account_usd"],
        p99_account_share=mc["p99_drawdown_usd"] / plan["account_usd"],
    )
    gates = {
        f"G{i}": dict(
            formal_status="NOT_EVALUATED_ON_QUALIFIED_DATA",
            formal_passed=None,
            diagnostic_value=None,
            diagnostic_threshold_met=None,
        )
        for i in range(1, 10)
    }
    gates["G1"].update(
        diagnostic_value=bootstrap["lower_5pct_r"],
        diagnostic_threshold_met=bootstrap["lower_5pct_r"] > rules["g1_bootstrap_lower_gt"],
        rule="lower bound >0R",
    )
    gates["G2"].update(reason="No certified matched random baseline; cannot calculate edge point")
    gates["G3"].update(reason="No certified matched random baseline; cannot calculate edge lower bound")
    gates["G4"].update(reason="Only part of eraD examined; erasA–C missing")
    gates["G5"].update(
        diagnostic_value=len(trades),
        diagnostic_threshold_met=len(trades) >= rules["g5_baskets_min"],
        rule="at least1000 qualified trades",
    )
    gates["G6"].update(reason="Real-tick gap coverage has not been qualified")
    gates["G7"].update(
        diagnostic_value=mc["p99_drawdown_usd"],
        diagnostic_threshold_met=mc["p99_account_share"] <= rules["g7_drawdown_account_share_max"],
        rule="p99 drawdown <=12% of USD20 = USD2.40",
    )
    gates["G8"].update(
        reason="No four-era fill-order diagnostics; generated event ordering does not prove real history"
    )
    gates["G9"].update(
        diagnostic_value=max(
            json.loads((HERE / "out" / n / "PARITY.json").read_text())["max_atr_error"]
            for n in plan["engineering_runs"]
        ),
        diagnostic_threshold_met=True,
        rule="ATR arithmetic matched on engineering windows only",
    )
    step6 = dict(
        candidate=plan["candidate"],
        assessed_utc=datetime.now(UTC).isoformat(),
        status="DIAGNOSTIC_COMPLETE_FORMAL_BLOCKED",
        formal_qualified=False,
        evaluation_complete=False,
        diagnostic_complete=True,
        gates=gates,
        source_sha256=sources,
        rule_sha256=sha(ROOT / plan["gates_path"]),
        windows=windows,
        bootstrap=bootstrap,
        monte_carlo=mc,
        pooled=dict(
            trades=len(trades),
            mean_r=float(trades.r_multiple.mean()),
            net_usc=float(trades.pnl_usc.sum()),
            buy=int(trades.side.eq(1).sum()),
            sell=int(trades.side.eq(-1).sum()),
        ),
        baseline_draws_completed=0,
        baseline_draws_per_era_required=plan["baseline_draws_per_era_required"],
        qualified_freeze_created=False,
        limits=plan["limits"],
    )
    if sources != candidate_sources():
        raise ValueError("Candidate source changed during evaluation")
    write(output / "STEP6.json", step6)
    # Read consumption metadata only. Do not read source.json.gz or any 2026 prices.
    registry = ROOT / "goldnix_step7/out/RESULT.json"
    old = json.loads(registry.read_text())
    consumed = [(old["protocol"]["start_inclusive"], old["protocol"]["end_exclusive"])]
    step7 = holdout_preflight(
        step6,
        current_source=candidate_sources(),
        freeze_verified=False,
        holdout_window=None,
        consumed_windows=consumed,
    )
    legacy = holdout_preflight(
        step6,
        current_source=candidate_sources(),
        freeze_verified=False,
        holdout_window=consumed[0],
        consumed_windows=consumed,
    )
    step7.update(
        consumed_registry_sha256=sha(registry),
        consumed_periods=consumed,
        legacy_period_check=legacy,
        collapse_statistics=None,
        earlier_examined_history_note="October/November2026 was also examined in earlier work; absence from this legacy Jan–Sep receipt does not certify freshness",
    )
    write(output / "STEP7.json", step7)
    (output / "REPORT.md").write_text(report(step6, step7))
    artifacts = {str(p.relative_to(output)): sha(p) for p in output.rglob("*") if p.is_file()}
    write(
        output / "MANIFEST.json",
        {"kind": "diagnostic audit snapshot; NOT qualifying Step6 freeze", "artifacts": artifacts},
    )
    (HERE / "step67/LATEST.json").write_text(json.dumps({"output": str(output)}, indent=2) + "\n")
    print(
        json.dumps(
            {
                "output": str(output),
                "step6_status": step6["status"],
                "pooled": step6["pooled"],
                "bootstrap": bootstrap,
                "monte_carlo": mc,
                "step7_status": step7["status"],
            }
        ),
        flush=True,
    )
    return output


def report(step6, step7):
    pooled, boot, mc = step6["pooled"], step6["bootstrap"], step6["monte_carlo"]
    lines = [
        "# Updated P01 Step6 and Step7",
        "",
        "**Step6 is not qualified. Step7 is blocked before holdout access.**",
        "",
        "The current M1 profit-protection candidate was replayed on the two previously examined generated-tick windows. Production EA parameters were unchanged.",
        "",
        f"- Trades: {pooled['trades']} ({pooled['buy']} BUY / {pooled['sell']} SELL).",
        f"- Mean return: {pooled['mean_r']:.6f}R; modeled net: {pooled['net_usc']:.2f}USC.",
        f"- Month-block bootstrap: {boot['resamples']:,} resamples; one-sided5% lower bound {boot['lower_5pct_r']:.6f}R; SE {boot['standard_error']:.6f}.",
        f"- Monte Carlo: {mc['paths']:,} one-year IID paths, {mc['trades_per_year']:,} trades/year; p99 drawdown ${mc['p99_drawdown_usd']:.4f} ({100 * mc['p99_account_share']:.2f}% of USD20).",
        "",
        "These are diagnostics, not qualified four-era gate values. The declared decision model uses0.01USC money precision and requested-level favourable TP fills. The previous native USD tester rounded to1USC and could fill TP favourably beyond its level, so these modeled cash totals can differ.",
        "",
        "| Gate | Diagnostic / missing evidence | Formal status |",
        "|---|---|---|",
    ]
    for name, gate in step6["gates"].items():
        detail = (
            gate.get("reason")
            or f"value={gate['diagnostic_value']}; numerical threshold met={gate['diagnostic_threshold_met']}"
        )
        lines.append(f"| {name} | {detail} | NOT QUALIFIED |")
    lines += [
        "",
        "## Limits",
        "",
        "There are only two calendar blocks, and the native windows end at22:00UTC on February29. January and February each start with a separate flat2000USC account. Treating those two blocks as an empirical bootstrap distribution cannot establish behavior across2005–2025. The IID Monte Carlo also omits new signal generation and calendar clustering; it does not prove future drawdown probabilities.",
        "",
        "No P01 matched random-entry baseline is available. G2/G3 were left unavailable; the protection-off ablation was not substituted. No trade-count threshold, risk threshold, bootstrap count or Monte Carlo count was lowered. No qualifying FROZEN file was created.",
        "",
        "## Step7 preflight",
        "",
        f"Status: **{step7['status']}**. Holdout payload read: **false**. Attempt consumed: **false**.",
        "",
        *[f"- {reason}" for reason in step7["blockers"]],
        "",
        "The legacy Jan–Sep2026 consumption receipt was checked without opening price data. Attempting to reuse that period is rejected as already consumed. October/November2026 was also examined earlier and is not assumed fresh. A new unused period has not been registered.",
        "",
        "Completion requires qualified four-era inputs and the matched baseline, unchanged G1–G9 evaluation, a matching qualifying freeze, then a registered untouched holdout evaluated once. This audit snapshot does not unlock Step7.",
        "",
        "See STEP6.json, STEP7.json, trades.csv, PLAN.json and MANIFEST.json for exact values, input/source hashes and provenance.",
    ]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    argparse.ArgumentParser(description=__doc__).parse_args()
    run()
