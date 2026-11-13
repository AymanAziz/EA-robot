"""Evaluate the four preregistered filters; preserve all outcomes and Step7 lock."""

import argparse
import csv
from datetime import UTC, datetime, timedelta
import hashlib
import json
from pathlib import Path
import shutil

import numpy as np
import pandas as pd

from goldnix_p01.data import read_ticks, minute_bars
from goldnix_p01.engine import Contract
from goldnix_p01.replay import TIMER_DTYPE, replay as original_replay
from goldnix_p01.statistics import monthly_bootstrap, chunked_drawdown
from goldnix_step6.bootstrap import paired_month_bootstrap
from .features import PLAN
from .replay import replay

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
RUNS = ["P01N_20261113T062543Z", "P01N_20261113T062008Z", "P01N_20261113T070748Z"]


def write(path, data):
    with path.open("x") as stream:
        json.dump(data, stream, indent=2, allow_nan=False)
        stream.write("\n")


def fingerprint(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(warmup_folder=None):
    output = HERE / "out" / datetime.now(UTC).strftime("S6_FILTERS_%Y%m%dT%H%M%SZ")
    output.mkdir(parents=True)
    plan_hash = fingerprint(HERE / "protocol.json")
    write(
        output / "STARTED.json",
        {
            "started_utc": datetime.now(UTC).isoformat(),
            "plan_sha256": plan_hash,
            "step7_approval_received": False,
            "step7_access": False,
            "warmup_revision": warmup_folder is not None,
        },
    )
    snapshot = output / "SOURCE"
    snapshot.mkdir()
    for source in list(HERE.glob("*.py")) + list(HERE.glob("*.json")):
        shutil.copy2(source, snapshot / source.name)
    names = ["P01", "COMMON_P01", *PLAN["candidates"]]
    pools = {name: [] for name in names}
    context = None
    if warmup_folder is not None:
        warmup_folder = Path(warmup_folder)
        info = json.loads((warmup_folder / "STARTED.json").read_text())
        if info["start"] != "2023.12.01" or info["end_exclusive"] != "2024.01.01":
            raise ValueError("Warmup must match the registered untraded December window")
        symbol = dict(csv.reader((warmup_folder / "native/symbol.csv").open()))
        warm_ticks, warm_audit = read_ticks(
            warmup_folder / "native/all_ticks.bin", server_offset=int(symbol["offset_seconds"])
        )
        receipt = dict(csv.reader((warmup_folder / "native/receipt.csv").open()))
        if (
            receipt["completed"] != "1"
            or receipt["tester"] != "1"
            or len(warm_ticks) != int(receipt["ticks"])
        ):
            raise ValueError("Incomplete warmup quote export")
        context = minute_bars(warm_ticks)
        write(
            output / "WARMUP.json",
            {
                "path": str(warmup_folder),
                "quote_audit": warm_audit,
                "m1_bars": len(context),
                "traded": False,
                "revision_sha256": fingerprint(HERE / "warmup_revision.json"),
            },
        )
        del warm_ticks
    windows, rows = [], []
    for number, run_id in enumerate(RUNS):
        folder = ROOT / "goldnix_p01/out" / run_id
        parity = json.loads((folder / "PARITY.json").read_text())
        if not parity["engineering_passed"]:
            raise ValueError("Native reference evidence must pass before candidate replay")
        native = folder / "native"
        symbol = dict(csv.reader((native / "symbol.csv").open()))
        offset = int(symbol["offset_seconds"])
        ticks, tick_audit = read_ticks(native / "all_ticks.bin", server_offset=offset)
        timers = np.fromfile(native / "timers.bin", TIMER_DTYPE)
        if (
            tick_audit["sha256"] != parity["data"]["sha256"]
            or fingerprint(native / "timers.bin") != parity["timers_sha256"]
        ):
            raise ValueError("Historical input hash mismatch")
        deals = pd.read_csv(native / "broker_deals.csv")
        if abs(deals[["commission_usc", "swap_usc", "fee_usc"]].to_numpy()).sum() > 1e-8:
            raise ValueError("Historical charges require a separate model")
        contract = Contract(
            tick=float(symbol["tick_size"]),
            stops=float(symbol["stops_level"]) * float(symbol["point"]),
            freeze=float(symbol["freeze_level"]) * float(symbol["point"]),
            leverage=float(symbol["leverage"]),
        )
        receipt = json.loads((folder / "STARTED.json").read_text())
        start = datetime.strptime(receipt["start"], "%Y.%m.%d").replace(tzinfo=UTC) - timedelta(
            seconds=offset
        )
        end = datetime.strptime(receipt["end_exclusive"], "%Y.%m.%d").replace(tzinfo=UTC) - timedelta(
            seconds=offset
        )
        label = ["January", "February", "March01_14"][number]
        windows.append(
            {
                "label": label,
                "run": run_id,
                "start_utc": start.isoformat(),
                "end_utc": end.isoformat(),
                "days": (end - start).total_seconds() / 86400,
                "quotes": len(ticks),
                "timers": len(timers),
                "tick_sha256": tick_audit["sha256"],
                "timer_sha256": parity["timers_sha256"],
            }
        )
        for name in names:
            result = replay(ticks, timers, contract, offset=offset, candidate=name, history_bars=context)
            if name == "P01":
                # Different code path, identical unfiltered outcomes on the actual input.
                expected = original_replay(ticks, timers, contract, offset=offset)
                assert result["trades"] == expected["trades"] and result["decisions"] == expected["decisions"]
                del expected
            trades = pd.DataFrame(result["trades"])
            if trades.empty:
                raise ValueError("No trades; cannot promote or compute finite performance evidence: " + name)
            if trades.exit_reason.eq("censored_boundary").any():
                raise ValueError("Test boundary censoring must be resolved explicitly")
            trades["exit_ts"] = pd.to_datetime(trades.exit_utc, unit="s", utc=True)
            trades["window"] = label
            trades.to_csv(output / f"{label}_{name}_trades.csv", index=False)
            pools[name].append(trades)
            row = dict(
                window=label,
                candidate=name,
                trades=len(trades),
                buy=int(trades.side.eq(1).sum()),
                sell=int(trades.side.eq(-1).sum()),
                mean_r=float(trades.r_multiple.mean()),
                pnl_usc=float(trades.pnl_usc.sum()),
            )
            rows.append(row)
            pd.DataFrame(rows).to_csv(output / "windows.csv", index=False)
            print(json.dumps(row), flush=True)
            del result
        if context is not None:
            context = pd.concat([context, minute_bars(ticks)], ignore_index=True)
            if context.epoch_seconds.duplicated().any() or (context.epoch_seconds.diff().dropna() <= 0).any():
                raise ValueError("Warmup/current windows overlap or are out of order")
        del ticks, timers
    source = json.loads((HERE / "replay_origin.json").read_text())
    if (
        fingerprint(ROOT / source["source"]) != source["sha256"]
        or fingerprint(HERE / "protocol.json") != plan_hash
    ):
        raise ValueError("Preserved reference or preregistered plan changed during evaluation")
    combined = {
        name: pd.concat(frames, ignore_index=True).sort_values("entry_utc") for name, frames in pools.items()
    }
    common = combined["COMMON_P01"].copy()
    common["draw"] = 0
    total_days = sum(w["days"] for w in windows)
    summary = {}
    for name, trades in combined.items():
        if trades.duplicated(["entry_utc", "side"]).any():
            raise ValueError("Overlapping trade population")
        trades.to_csv(output / f"{name}_trades.csv", index=False)
        statistics = PLAN["statistics"]
        boot = monthly_bootstrap(
            trades.r_multiple,
            trades.exit_ts.dt.strftime("%Y-%m"),
            calendar=["2024-01", "2024-02", "2024-03"],
            resamples=statistics["bootstrap_resamples"],
            seed=statistics["bootstrap_seed"],
        )
        comparison = paired_month_bootstrap(
            trades,
            common,
            start="2024-01-01",
            end="2024-03-14",
            resamples=statistics["bootstrap_resamples"],
            seed=statistics["bootstrap_seed"],
        )
        mc = chunked_drawdown(
            trades.pnl_usc.to_numpy() / 100,
            trades_per_year=max(1, round(len(trades) * 365.2425 / total_days)),
            simulations=statistics["monte_carlo_paths"],
            seed=statistics["monte_carlo_seed"],
        )
        summary[name] = dict(
            trades=len(trades),
            buy=int(trades.side.eq(1).sum()),
            sell=int(trades.side.eq(-1).sum()),
            mean_r=float(trades.r_multiple.mean()),
            pnl_usc=float(trades.pnl_usc.sum()),
            bootstrap=boot,
            mc=mc,
            mean_delta_vs_common=comparison["edge_point"],
            paired_month_delta_lower=comparison["edge_lower"],
            retention_vs_common=len(trades) / len(common),
        )
        print(json.dumps({"pooled": name, **summary[name]}), flush=True)
    screened = []
    table = pd.DataFrame(rows)
    for name in PLAN["candidates"]:
        comparisons = []
        for label in table.window.unique():
            baseline = table[(table.window == label) & (table.candidate == "COMMON_P01")].iloc[0]
            candidate = table[(table.window == label) & (table.candidate == name)].iloc[0]
            comparisons.append(
                dict(
                    window=label,
                    mean_r_improved=bool(candidate.mean_r > baseline.mean_r),
                    net_usc_improved=bool(candidate.pnl_usc > baseline.pnl_usc),
                )
            )
        checks = dict(
            all_windows_better=all(c["mean_r_improved"] and c["net_usc_improved"] for c in comparisons),
            p99_drawdown_lower=summary[name]["mc"]["p99_drawdown_usd"]
            < summary["COMMON_P01"]["mc"]["p99_drawdown_usd"],
            both_sides_observed=summary[name]["buy"] > 0 and summary[name]["sell"] > 0,
        )
        summary[name]["improvement_screen"] = dict(
            passed=all(checks.values()), checks=checks, windows=comparisons
        )
        if all(checks.values()):
            screened.append(name)
    selected = max(screened, key=lambda name: summary[name]["mean_r"]) if screened else None
    result = dict(
        status="EXPLORATORY_SCREEN_COMPLETE",
        formal_step6_passed=False,
        selected_for_further_step6_evaluation=selected,
        windows=windows,
        results=summary,
        step7_approval_required=True,
        step7_approval_received=False,
        step7_run=False,
        active_demo_candidate="P01_UNCHANGED",
        preceding_history_used=warmup_folder is not None,
        limitations=[
            "Generated quotes and3 partial/reused calendar blocks, all inside eraD",
            "Four fixed candidates after at least82 prior variants; selection is exploratory",
            "Original1000-trade/four-era/matched-baseline requirements remain unmet",
            "One-year IID drawdown reductions may partly reflect fewer trades; per-trade and per-window comparisons are retained",
            "No formal Step6 freeze or Step7 evidence is created",
        ],
    )
    write(output / "RESULT.json", result)
    write(
        output / "MANIFEST.json",
        {
            "kind": "exploratory audit, not qualifying freeze",
            "sha256": {str(p.relative_to(output)): fingerprint(p) for p in output.rglob("*") if p.is_file()},
        },
    )
    (HERE / "LATEST.json").write_text(json.dumps({"output": str(output)}, indent=2) + "\n")
    print(
        json.dumps(
            {"output": str(output), "selected": selected, "formal_step6_passed": False, "step7_run": False}
        ),
        flush=True,
    )
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--warmup", type=Path)
    run(parser.parse_args().warmup)
