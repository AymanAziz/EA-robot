"""Evaluate the single registered selection against matched random-entry schedules."""

import hashlib
import json
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from gates.verdict import evaluate_gates
from goldnix_research.screen import candidate_eras
from goldnix_round2.execution import Market
from goldnix_round2.runner import execution_config, prepared_eras
from goldnix_step6.baseline import sample_schedules, schedule_is_valid
from goldnix_step6.bootstrap import paired_month_bootstrap
from goldnix_step7.runner import preflight
from ingest.gaps import find_gaps
from params.config import load_yaml

ROOT = Path(__file__).resolve().parents[1]


def run_baseline(bars, config, signal_trades, *, draws, sweeps, seed):
    market = Market(bars, find_gaps(bars))
    records = []
    for direction in (1, -1):
        if not signal_trades.dir.eq("BUY" if direction == 1 else "SELL").any():
            continue
        for index in range(len(bars) - 1):
            if market.eligible(index, direction, config):
                records.append(market.trade(index, direction, config))
    pool = pd.DataFrame(records)
    lookup = {(row.entry_ts, row.dir): i for i, row in enumerate(pool.itertuples())}
    initial = [lookup[(row.entry_ts, row.dir)] for row in signal_trades.itertuples()]
    # Every observed trade must be reproducible by the baseline's fill engine.
    columns = ["entry_ts", "exit_ts", "dir", "entry", "exit", "r_multiple"]
    pd.testing.assert_frame_equal(pool.iloc[initial][columns].reset_index(drop=True),
                                  signal_trades[columns].reset_index(drop=True),
                                  check_dtype=False, rtol=1e-10, atol=1e-10)
    baseline, diagnostics = sample_schedules(pool, initial_ids=initial, draws=draws,
                                             sweeps=sweeps, seed=seed,
                                             daily_halt_r=config["daily_halt_r"])
    counts = signal_trades.dir.value_counts()
    expected = sum(counts[d] ** 2 / pool.dir.eq(d).sum() for d in counts.index) / len(initial)
    diagnostics["unconstrained_expected_retention"] = expected
    diagnostics["eligible_pool_baskets"] = len(pool)
    for _, draw in baseline.groupby("draw"):
        if not schedule_is_valid(draw, daily_halt_r=config["daily_halt_r"]):
            raise AssertionError("Random schedule violates the execution envelope")
        if draw.dir.value_counts().to_dict() != counts.to_dict():
            raise AssertionError("Random schedule changes direction quotas")
    return baseline, diagnostics


def sampler_report(diagnostics, protocol):
    difference = diagnostics.final_mean_r - diagnostics.midpoint_mean_r
    se = float(difference.std(ddof=1) / np.sqrt(len(difference)))
    excess = float((diagnostics.initial_retention - diagnostics.unconstrained_expected_retention).mean())
    return {
        "mean_acceptance": float(diagnostics.acceptance_rate.mean()),
        "mean_initial_retention": float(diagnostics.initial_retention.mean()),
        "retention_excess_vs_unconstrained": excess,
        "midpoint_to_final_difference": float(difference.mean()), "difference_se": se,
        "mixing_warning": bool(excess > protocol["sampler_retention_excess_warning"]
                               or abs(difference.mean()) > protocol["sampler_midpoint_difference_se_warning"] * se + 1e-12),
        "limitation": "Finite MCMC burn-in approximates uniform feasible schedules; diagnostics do not prove convergence",
    }


def assemble_result(screen, bootstrap, samplers):
    inputs = {
        "account_usd": 20., "bootstrap_lower_bound": bootstrap["mean_lower"],
        "signal_minus_baseline": bootstrap["edge_point"], "edge_lower_bound": bootstrap["edge_lower"],
        "positive_eras": screen["positive_eras"], "baskets": screen["baskets"],
        "gap_risk_share": screen["gap_risk_share"], "max_fill_delta_pp": screen["max_fill_delta_pp"],
        "atr_parity": screen["G9"],
    }
    rules = load_yaml(ROOT / "goldnix/gates/rules.yaml")
    scenarios = {}
    for name, key in (("verified_exposure", "p99_usd_at_verified_1oz"),
                      ("product_scenario", "p99_usd_at_product_scenario_0_01oz")):
        scenario_inputs = {**inputs, "mc_p99_drawdown_usd": screen[key]}
        result = evaluate_gates(scenario_inputs, rules)
        scenarios[name] = {"numerical_verdict": result.verdict, "gates": result.gates,
                           "inputs": scenario_inputs}
    return {
        "candidate_id": screen["id"], "candidate": screen["candidate"],
        "evaluation_complete": True, "approval": False, "account_verified": False,
        "status": "EXPLORATORY_EVALUATION_COMPLETE", "holdout_access": False,
        "bootstrap": bootstrap, "selection_adjusted_mean_lower": screen["bootstrap"]["selection_lower"],
        "selection_adjusted_positive": screen["bootstrap"]["selection_lower"] > 0,
        "samplers": samplers, "sampler_has_warning": any(x["mixing_warning"] for x in samplers.values()),
        **scenarios,
    }


def _worker(number, name, bars, config, observed, protocol):
    print(f"{name}: matching {len(observed)} baskets and risk eligibility", flush=True)
    baseline, diagnostics = run_baseline(bars, config, observed, draws=protocol["baseline_draws"],
                                         sweeps=protocol["baseline_sweeps"],
                                         seed=protocol["baseline_seed"] + number * 1000)
    baseline["era"], diagnostics["era"] = name, name
    print(f"{name}: all {protocol['baseline_draws']} random schedules validated", flush=True)
    return name, baseline, diagnostics, sampler_report(diagnostics, protocol)


def main():
    preflight(ROOT)
    directory = ROOT / "goldnix_round2"
    summary = json.loads((directory / "out/SUMMARY.json").read_text())
    selected = summary["selected"]
    if selected is None:
        raise ValueError("No candidate qualified under the recorded selection rule")
    screen = json.loads((directory / f"out/{selected}/metrics.json").read_text())
    protocol = {**load_yaml(ROOT / "goldnix_step6/protocol.yaml"),
                **json.loads((directory / "protocol.json").read_text())}
    if protocol["holdout_access"]:
        raise ValueError("Holdout access is prohibited in this experiment")
    manifest = dict(summary["source_sha256"])
    additions = ["goldnix_round2/full_evaluation.py", "goldnix_round2/tests/test_full_evaluation.py",
                 "goldnix_round2/out/SUMMARY.json", f"goldnix_round2/out/{selected}/metrics.json",
                 f"goldnix_round2/out/{selected}/trades.csv", "goldnix_step6/baseline.py",
                 "goldnix_step6/bootstrap.py", "goldnix_step6/protocol.yaml", "goldnix/gates/verdict.py",
                 "goldnix/gates/rules.yaml"]
    for name in additions:
        manifest[name] = hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
    output = directory / "out/full_evaluation"
    output.mkdir(exist_ok=False)
    for name, digest in manifest.items():
        data = (ROOT / name).read_bytes()
        if hashlib.sha256(data).hexdigest() != digest:
            raise PermissionError("Screen source changed before full evaluation")
        copy = output / "source" / name
        copy.parent.mkdir(parents=True, exist_ok=True)
        copy.write_bytes(data)
    (output / "STARTED.json").write_text(json.dumps({"candidate_id": selected,
        "started_utc": datetime.now(UTC).isoformat(), "source_sha256": manifest}, indent=2) + "\n")
    candidate = screen["candidate"]
    eras = prepared_eras(candidate_eras(ROOT, candidate, protocol), candidate)
    observed = pd.read_csv(directory / f"out/{selected}/trades.csv",
                           parse_dates=["entry_ts", "exit_ts"], keep_default_na=False)
    config = execution_config(load_yaml(ROOT / "goldnix/params/decision.yaml"), candidate)
    baselines, samplers = {}, {}
    with ProcessPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(_worker, number, name, bars, config,
                               observed.loc[observed.era.eq(name)], protocol)
                   for number, (name, bars) in enumerate(eras.items())]
        for future in as_completed(futures):
            name, baseline, diagnostics, sampler = future.result()
            baselines[name], samplers[name] = baseline, sampler
            baseline.to_csv(output / f"{name}_baseline.csv.gz", index=False, compression="gzip")
            diagnostics.to_csv(output / f"{name}_diagnostics.csv", index=False)
            (output / f"{name}_sampler.json").write_text(json.dumps(sampler, indent=2) + "\n")
    baseline = pd.concat([baselines[name] for name in eras], ignore_index=True)
    bootstrap = paired_month_bootstrap(observed, baseline,
        start=min(f.timestamp_utc.min() for f in eras.values()),
        end=max(f.timestamp_utc.max() for f in eras.values()),
        resamples=protocol["bootstrap_resamples"], seed=protocol["bootstrap_seed"])
    result = assemble_result(screen, bootstrap, samplers)
    result.update({"completed_utc": datetime.now(UTC).isoformat(), "source_sha256": manifest,
                   "baseline_draws_per_era": protocol["baseline_draws"],
                   "cumulative_trials": protocol["trial_count"]})
    preflight(ROOT)
    for name, digest in manifest.items():
        if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != digest:
            raise PermissionError("Source changed during full evaluation")
    (output / "RESULT.json").write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n")
    print(json.dumps({"candidate_id": selected, "bootstrap": bootstrap,
                      "verified_verdict": result["verified_exposure"]["numerical_verdict"],
                      "scenario_verdict": result["product_scenario"]["numerical_verdict"],
                      "sampler_warning": result["sampler_has_warning"], "approval": False}), flush=True)


if __name__ == "__main__":
    main()
