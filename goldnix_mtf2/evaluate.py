"""Frozen twelve-candidate research batch and conditional full Step 6 evaluation."""

import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from gates.verdict import evaluate_gates
from goldnix_mtf.data import CACHE, ROOT, digest
from goldnix_mtf.evaluate import preserved_freezes, sampler_statistics, statistics
from goldnix_mtf.method import features
from goldnix_mtf2.method import Market, confirmation_signals
from goldnix_research.screen import screen_statistics
from goldnix_step6.baseline import sample_schedules, schedule_is_valid
from goldnix_step6.bootstrap import paired_month_bootstrap
from goldnix_step6.freeze import source_manifest
from metrics.montecarlo import monte_carlo_drawdown
from params.config import load_yaml

DIRECTORY = ROOT / "goldnix_mtf2"


def write_json(path, value):
    payload = json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"
    with Path(path).open("x") as handle:
        handle.write(payload)


def manifest():
    files = []
    for folder in ("goldnix_mtf2", "goldnix_mtf", "goldnix_research", "goldnix_round2", "goldnix_step7"):
        for path in (ROOT / folder).rglob("*"):
            if path.is_file() and path.suffix in (".py", ".json") and "out" not in path.relative_to(ROOT / folder).parts:
                files.append(path)
    return {**source_manifest(ROOT), **{p.relative_to(ROOT).as_posix(): digest(p) for p in files}}


def verify_inputs(protocol):
    preserved_freezes()
    if protocol["holdout_performance_access"] or digest(ROOT / "goldnix/gates/rules.yaml") != protocol["gates_sha256"]:
        raise PermissionError("Gate or holdout restriction changed")
    if digest(ROOT / "goldnix_mtf/protocol.json") != protocol["base_feature_protocol_sha256"]:
        raise PermissionError("Base feature settings changed")
    if digest(CACHE / "MANIFEST.json") != protocol["data_manifest_sha256"]:
        raise PermissionError("Input manifest changed")
    data = json.loads((CACHE / "MANIFEST.json").read_text())
    if digest(CACHE / "validated.pkl") != data["validated_sha256"]:
        raise PermissionError("Input prices changed")
    prior = json.loads((ROOT / "goldnix_mtf/out/U01_final_review/RESULT.json").read_text())
    if not prior["gates"]["G9"]["passed"] or digest(ROOT / prior["g9_evidence"]) != prior["g9_evidence_sha256"]:
        raise PermissionError("Native parity evidence unavailable")
    for name in ("goldnix_mtf/method.py", "goldnix/params/atr.py"):
        if digest(ROOT / name) != prior["source_sha256"][name]:
            raise PermissionError("Parity-tested indicator implementation changed")
    return data


def screen(market, signal, candidate, protocol):
    frames, eras = [], {}
    for era, bounds in protocol["eras_exclusive_end"].items():
        trades = market.simulate(signal, candidate, era, bounds)
        alternate = market.simulate(signal, candidate, era, bounds, "target_first")
        if trades.empty:
            raise ValueError(f"{candidate['id']} has no trades in era {era}; needs explicit empty-era handling")
        eras[era] = {**statistics(trades), "fill_delta_pp": float(abs(trades.r_multiple.gt(0).mean()
            - alternate.r_multiple.gt(0).mean()) * 100)}
        frames.append(trades)
    trades = pd.concat(frames, ignore_index=True)
    boot = screen_statistics(trades, start="2005-06-01T00:00Z", end="2025-12-31T23:59:59Z",
        trials=protocol["cumulative_registered_variants"], resamples=protocol["bootstrap_resamples"],
        seed=protocol["bootstrap_seed"])
    years = (pd.Timestamp("2026-01-01T00:00Z") - pd.Timestamp("2005-06-01T00:00Z")).total_seconds() / (365.2425 * 86400)
    risk = monte_carlo_drawdown(trades.pnl_usd.to_numpy(), trades_per_year=max(1, round(len(trades) / years)),
        simulations=protocol["monte_carlo_paths"], seed=protocol["monte_carlo_seed"])
    pooled = statistics(trades)
    positive = sum(value["mean_r"] > 0 for value in eras.values())
    fill = max(value["fill_delta_pp"] for value in eras.values())
    gates = {"G1": boot["mean_lower"] > 0, "G4": positive >= 3, "G5": len(trades) >= 1000,
             "G6": pooled["gap_risk_share"] <= .1, "G7": risk.p99_max_drawdown_usd <= 2.4,
             "G8": fill <= 8., "G9": True}
    return {"candidate": candidate, "pooled": pooled, "eras": eras, "bootstrap": boot,
            "positive_eras": positive, "max_fill_delta_pp": fill, "gates": gates,
            "p99_drawdown_usd": risk.p99_max_drawdown_usd, "mc_paths": risk.simulations,
            "eligible_for_full_evaluation": all(gates.values()), "not_evaluated": ["G2", "G3"],
            "approval": False, "by_direction": {d: statistics(trades.loc[trades.dir.eq(d)]) for d in ("BUY", "SELL")}}, trades


def full_evaluation(market, result, observed, protocol, output):
    candidate = result["candidate"]
    all_baselines, samplers = [], {}
    for number, (era, bounds) in enumerate(protocol["eras_exclusive_end"].items()):
        trades = observed.loc[observed.era.eq(era)]
        directions = [d for d in (1, -1) if trades.dir.eq("BUY" if d == 1 else "SELL").any()]
        print(f"{candidate['id']} {era}: building matched execution pool", flush=True)
        pool = market.pool(candidate, era, bounds, directions)
        lookup = {(r.entry_index, r.dir): i for i, r in enumerate(pool.itertuples())}
        initial = [lookup[(r.entry_index, r.dir)] for r in trades.itertuples()]
        columns = ["entry_index", "exit_index", "dir", "entry", "exit", "r_multiple"]
        pd.testing.assert_frame_equal(pool.iloc[initial][columns].reset_index(drop=True),
            trades[columns].reset_index(drop=True), check_dtype=False, rtol=1e-10, atol=1e-10)
        baseline, diagnostics = sample_schedules(pool, initial_ids=initial, draws=protocol["baseline_draws"],
            sweeps=protocol["baseline_sweeps"], seed=protocol["baseline_seed"] + number * 1000,
            daily_halt_r=protocol["daily_halt_r"])
        for _, frame in baseline.groupby("draw"):
            if not schedule_is_valid(frame, daily_halt_r=protocol["daily_halt_r"]) or frame.dir.value_counts().to_dict() != trades.dir.value_counts().to_dict():
                raise AssertionError("Invalid matched baseline schedule")
        samplers[era] = sampler_statistics(diagnostics, pool, trades, protocol)
        baseline.to_csv(output / f"{era}_baseline.csv.gz", index=False, compression="gzip")
        diagnostics.to_csv(output / f"{era}_samplers.csv", index=False)
        all_baselines.append(baseline)
        print(f"{candidate['id']} {era}: 200 baseline schedules validated", flush=True)
    baseline = pd.concat(all_baselines, ignore_index=True)
    boot = paired_month_bootstrap(observed, baseline, start="2005-06-01T00:00Z", end="2025-12-31T23:59:59Z",
        resamples=protocol["bootstrap_resamples"], seed=protocol["bootstrap_seed"])
    inputs = {"account_usd": 20., "bootstrap_lower_bound": boot["mean_lower"],
        "signal_minus_baseline": boot["edge_point"], "edge_lower_bound": boot["edge_lower"],
        "positive_eras": result["positive_eras"], "baskets": len(observed),
        "gap_risk_share": result["pooled"]["gap_risk_share"], "mc_p99_drawdown_usd": result["p99_drawdown_usd"],
        "max_fill_delta_pp": result["max_fill_delta_pp"], "atr_parity": True}
    verdict = evaluate_gates(inputs, load_yaml(ROOT / "goldnix/gates/rules.yaml"))
    complete = {**result, "evaluation_complete": True, "not_evaluated": [], "raw_gate_verdict": verdict.verdict,
        "gates": verdict.gates, "gate_inputs": inputs, "full_bootstrap": boot, "samplers": samplers,
        "sampler_has_warning": any(s["mixing_warning"] for s in samplers.values()),
        "selection_adjusted_positive": result["bootstrap"]["selection_lower"] > 0,
        "approval": False, "status": "EXPLORATORY_FULL_EVALUATION_COMPLETE"}
    write_json(output / "RESULT.json", complete)
    return complete


def main():
    protocol = json.loads((DIRECTORY / "protocol.json").read_text())
    data = verify_inputs(protocol)
    source = manifest()
    output = DIRECTORY / "out/batch_12"
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "STARTED.json", {"started_utc": datetime.now(UTC).isoformat(),
        "protocol_sha256": digest(DIRECTORY / "protocol.json"), "source_sha256": source})
    for relative, expected in source.items():
        target = output / "source" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / relative).read_bytes())
        if digest(target) != expected:
            raise PermissionError("Source snapshot failed")
    write_json(output / "DATA_MANIFEST.json", data)
    bars = pd.read_pickle(CACHE / "validated.pkl")
    prepared = features(bars, json.loads((ROOT / "goldnix_mtf/protocol.json").read_text()))
    market = Market(bars, prepared, protocol)
    signals = {}
    for kind in ("retest", "hold"):
        signals[kind], audit = confirmation_signals(bars, prepared, kind, protocol)
        audit.to_csv(output / f"{kind}_setups.csv.gz", index=False, compression="gzip")
        print(f"{kind}: {np.count_nonzero(signals[kind]):,} confirmed intents before risk/cost/position filters", flush=True)
    results, trades_by_id = [], {}
    for candidate in protocol["candidate_configs"]:
        result, trades = screen(market, signals[candidate["confirmation"]], candidate, protocol)
        folder = output / candidate["id"]
        folder.mkdir()
        write_json(folder / "SCREEN.json", result)
        trades.to_csv(folder / "trades.csv", index=False)
        results.append(result)
        trades_by_id[candidate["id"]] = trades
        print(json.dumps({"id": candidate["id"], "trades": len(trades), "mean_r": result["pooled"]["mean_r"],
            "mean_lower": result["bootstrap"]["mean_lower"], "positive_eras": result["positive_eras"],
            "gates": result["gates"], "qualifies": result["eligible_for_full_evaluation"]}), flush=True)
    qualified = sorted([r for r in results if r["eligible_for_full_evaluation"]],
                       key=lambda r: (r["bootstrap"]["selection_lower"], r["candidate"]["id"]), reverse=True)[:2]
    full = {}
    for result in qualified:
        candidate_id = result["candidate"]["id"]
        destination = output / candidate_id / "full"
        destination.mkdir()
        full[candidate_id] = full_evaluation(market, result, trades_by_id[candidate_id], protocol, destination)
    verify_inputs(protocol)
    if manifest() != source:
        raise PermissionError("Source changed while batch was running")
    summary = {"status": "REGISTERED_BATCH_COMPLETE", "completed_utc": datetime.now(UTC).isoformat(),
        "new_trials": 12, "cumulative_registered_trials": protocol["cumulative_registered_variants"],
        "results": results, "full_evaluations": full, "approval": False,
        "raw_passes": [name for name, r in full.items() if r["raw_gate_verdict"] == "PASS"],
        "holdout_performance_access": False, "source_sha256": source}
    write_json(output / "SUMMARY.json", summary)
    write_json(output / "FROZEN.json", {"created_utc": summary["completed_utc"], "approval": False,
        "artifact_sha256": {p.relative_to(output).as_posix(): digest(p) for p in output.rglob("*") if p.is_file()}})
    print(json.dumps({"status": summary["status"], "raw_passes": summary["raw_passes"]}), flush=True)


if __name__ == "__main__":
    main()
