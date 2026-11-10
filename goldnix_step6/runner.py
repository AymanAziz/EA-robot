"""Complete corrected G1-G9 reports without changing either strategy configuration."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd

from gates.freeze import verify_freeze
from gates.verdict import evaluate_gates
from ingest.gaps import find_gaps
from ingest.ingest import load_bars
from metrics.montecarlo import monte_carlo_drawdown
from metrics.report import longest_losing_streak, time_in_market_share
from params.config import dump_yaml, load_yaml
from sim.engine import prepare_bars, run_engine
from goldnix_v2.signal import apply_v2_confirmation
from goldnix_step6.baseline import run_baseline, schedule_is_valid
from goldnix_step6.bootstrap import paired_month_bootstrap
from goldnix_step6.freeze import assert_sources_committed, freeze_run, source_manifest, verify_run

ROOT = Path(__file__).resolve().parents[1]
DATA_NAME = "xauusd_h1_20030505_20251231_bid_ask.csv"


def approval_verdict(numerical_verdict, *, sampler_warning):
    """Keep numerical gate results, but do not approve an unreliable simulation."""
    if numerical_verdict == "PASS" and sampler_warning:
        return "PROVISIONAL_SAMPLER_WARNING"
    return numerical_verdict


def _report(trades, bars, config, bootstrap):
    distance = np.maximum(trades.atr.to_numpy() * config["stop_atr"], config["min_distance_usd"])
    cost_r = float(np.mean(trades.spread_paid.to_numpy() / distance))
    reward_r = config["target_atr"] / config["stop_atr"]
    return {
        "baskets": len(trades), "win_rate": float(trades.r_multiple.gt(0).mean()),
        "mean_r": float(trades.r_multiple.mean()), "bootstrap": bootstrap,
        "longs": int(trades.dir.eq("BUY").sum()), "shorts": int(trades.dir.eq("SELL").sum()),
        "long_mean_r": float(trades.loc[trades.dir.eq("BUY"), "r_multiple"].mean()),
        "short_mean_r": float(trades.loc[trades.dir.eq("SELL"), "r_multiple"].mean()),
        "longest_losing_streak": longest_losing_streak(trades.r_multiple),
        "mean_mae_r": float(trades.mae_r.mean()), "mean_mfe_r": float(trades.mfe_r.mean()),
        "time_in_market_share": time_in_market_share(trades, bars),
        "spread_paid_usd": float(trades.spread_paid.sum()),
        "gap_risk_share": float(trades["flags"].eq("gap_risk").mean()),
        "mean_atr": float(trades.atr.mean()), "mean_spread_r": cost_r,
        "reference_break_even_win_rate": (1 + cost_r) / (1 + reward_r),
        "reference_win_rate_for_0_15r": (1.15 + cost_r) / (1 + reward_r),
        "reference_assumption": "Fixed stop/target-only outcomes, excluding gaps and timed exits",
    }


def evaluate_study(eras, config, protocol, *, gaps, atr_parity):
    """Compute all required metrics and gates for the complete supplied study."""
    trade_frames, baseline_frames, diagnostic_frames, reports = [], [], [], {}
    for number, (era, bars) in enumerate(eras.items()):
        print(f"{era}: computing baseline with matched execution envelope", flush=True)
        simulation = run_engine(bars, config, gaps=gaps)
        trades = simulation.trades
        baseline, diagnostics = run_baseline(
            bars, config, trades, draws=protocol["baseline_draws"],
            sweeps=protocol["baseline_sweeps"], seed=protocol["baseline_seed"] + number * 1000,
        )
        # Validate all draws, including exact direction quotas, before using any result.
        for _, draw in baseline.groupby("draw"):
            if not schedule_is_valid(draw, daily_halt_r=config["daily_halt_r"]):
                raise AssertionError("Generated baseline violated execution envelope")
            if draw.dir.value_counts().to_dict() != trades.dir.value_counts().to_dict():
                raise AssertionError("Baseline direction counts differ from signal")
        baseline["era"], diagnostics["era"] = era, era
        trade_frames.append(trades)
        baseline_frames.append(baseline)
        diagnostic_frames.append(diagnostics)
        bootstrap = paired_month_bootstrap(
            trades, baseline, start=bars.timestamp_utc.min(), end=bars.timestamp_utc.max(),
            resamples=protocol["bootstrap_resamples"], seed=protocol["bootstrap_seed"] + number + 1,
        )
        report = _report(trades, bars, config, bootstrap)
        optimistic = run_engine(bars, {**config, "fill_policy": "target_first"}, gaps=gaps).trades
        report["fill_delta_pp"] = abs(float(optimistic.r_multiple.gt(0).mean()) - report["win_rate"]) * 100
        report["signals_after_confirmation"] = simulation.signals
        report["engine_cost_skip_share"] = simulation.skipped_by_vol_ceiling / max(1, simulation.signals)
        if "raw_signal" in bars:
            raw = bars.raw_signal.isin([-1, 1])
            confirmed = ((bars.raw_signal.eq(1) & bars.h4_oscillator.gt(0))
                         | (bars.raw_signal.eq(-1) & bars.h4_oscillator.lt(0)))
            report["raw_crosses"] = int(raw.sum())
            report["cost_skip_share_of_raw_crosses"] = float((confirmed & ~bars.cost_eligible).sum() / max(1, raw.sum()))
        diff = diagnostics.final_mean_r - diagnostics.midpoint_mean_r
        se = float(diff.std(ddof=1) / np.sqrt(len(diff)))
        excess = float((diagnostics.initial_retention - diagnostics.unconstrained_expected_retention).mean())
        report["sampler"] = {
            "mean_acceptance": float(diagnostics.acceptance_rate.mean()),
            "mean_initial_retention": float(diagnostics.initial_retention.mean()),
            "retention_excess_vs_unconstrained": excess,
            "midpoint_to_final_difference": float(diff.mean()), "difference_se": se,
            "mixing_warning": bool(excess > protocol["sampler_retention_excess_warning"]
                                   or abs(diff.mean()) > protocol["sampler_midpoint_difference_se_warning"] * se + 1e-12),
            "limitation": "Finite MCMC burn-in approximates uniform feasible schedules; diagnostics do not prove convergence",
        }
        reports[era] = report
        print(f"{era}: {len(trades)} baskets; all {protocol['baseline_draws']} baseline schedules valid", flush=True)
    trades = pd.concat(trade_frames, ignore_index=True)
    baseline = pd.concat(baseline_frames, ignore_index=True)
    diagnostics = pd.concat(diagnostic_frames, ignore_index=True)
    bars = pd.concat(eras.values(), ignore_index=True)
    start, end = bars.timestamp_utc.min(), bars.timestamp_utc.max()
    bootstrap = paired_month_bootstrap(trades, baseline, start=start, end=end,
                                      resamples=protocol["bootstrap_resamples"], seed=protocol["bootstrap_seed"])
    pooled = _report(trades, bars, config, bootstrap)
    years = ((end - start).total_seconds() + 3600) / (365.2425 * 86400)
    rate = len(trades) / years
    distance = np.maximum(trades.atr.to_numpy() * config["stop_atr"], config["min_distance_usd"])
    risk = monte_carlo_drawdown(trades.r_multiple.to_numpy() * distance * protocol["usd_per_price_unit"],
                               trades_per_year=max(1, round(rate)), simulations=protocol["monte_carlo_paths"],
                               seed=protocol["monte_carlo_seed"])
    inputs = {
        "account_usd": protocol["account_usd"], "bootstrap_lower_bound": bootstrap["mean_lower"],
        "signal_minus_baseline": bootstrap["edge_point"], "edge_lower_bound": bootstrap["edge_lower"],
        "positive_eras": sum(x["mean_r"] > 0 for x in reports.values()), "baskets": len(trades),
        "gap_risk_share": pooled["gap_risk_share"], "mc_p99_drawdown_usd": risk.p99_max_drawdown_usd,
        "max_fill_delta_pp": max(x["fill_delta_pp"] for x in reports.values()), "atr_parity": atr_parity,
    }
    verdict = evaluate_gates(inputs, load_yaml(ROOT / "goldnix/gates/rules.yaml"))
    warning = any(x["sampler"]["mixing_warning"] for x in reports.values())
    return {
        "evaluation_complete": True, "numerical_gate_verdict": verdict.verdict,
        "verdict": approval_verdict(verdict.verdict, sampler_warning=warning), "gates": verdict.gates,
        "gate_inputs": inputs, "eras": reports, "pooled": pooled,
        "monte_carlo": {"p99_usd": risk.p99_max_drawdown_usd, "paths": risk.simulations,
                        "observed_rate_per_year": rate, "trades_per_year": risk.trades_per_year},
        "sampler_has_warning": warning,
        "holdout_run": False,
    }, trades, baseline, diagnostics


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--study", choices=["V1", "V2"], required=True)
    args = parser.parse_args()
    if not verify_freeze(ROOT / "goldnix"):
        raise RuntimeError("V1 freeze changed")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    assert_sources_committed(ROOT, commit)
    protocol = load_yaml(ROOT / "goldnix_step6/protocol.yaml")
    config_path = ROOT / ("goldnix/params/decision.yaml" if args.study == "V1" else "goldnix_v2/decision.yaml")
    config = load_yaml(config_path)
    era_config = load_yaml(ROOT / "goldnix/data/eras.yaml")
    data_path = ROOT / "goldnix/data/clean" / DATA_NAME
    raw_path = ROOT / "goldnix/data/raw" / DATA_NAME
    hashes = {"raw": hashlib.sha256(raw_path.read_bytes()).hexdigest(),
              "clean": hashlib.sha256(data_path.read_bytes()).hexdigest()}
    manifest = source_manifest(ROOT)
    fingerprint = hashlib.sha256(json.dumps({"source": manifest, "data": hashes,
                                              "study": args.study}, sort_keys=True).encode()).hexdigest()[:12]
    output = ROOT / "goldnix_step6/out" / f"{args.study}_{fingerprint}"
    output.mkdir(parents=True, exist_ok=False)
    bars = load_bars(data_path)
    gaps = find_gaps(bars)
    eras = {}
    for name, window in era_config["eras"].items():
        start, end = pd.Timestamp(window["start_utc"]), pd.Timestamp(window["end_utc"])
        times = pd.DatetimeIndex(bars.timestamp_utc)
        first, last = times.searchsorted(start), times.searchsorted(end, side="right")
        warmup = config.get("warmup_h1_bars", era_config["warmup_bars"])
        frame = bars.iloc[max(0, first - warmup):last].copy()
        frame["era"] = name
        frame = prepare_bars(frame, config)
        if args.study == "V2":
            frame = apply_v2_confirmation(frame, h4_period=config["h4_aroon_period"],
                                          ties=config["ties"], max_spread_atr=config["vol_ceiling_atr"],
                                          server_timezone=config["server_timezone"])
        eras[name] = frame.loc[frame.timestamp_utc.between(start, end)].reset_index(drop=True)
    # ATR code and selected method are unchanged; freeze verification authenticates the dependency.
    parity_path = ROOT / "goldnix/parity/ATR_PARITY_RESULT.md"
    parity = "- Result: PASS" in parity_path.read_text()
    result, trades, baseline, diagnostics = evaluate_study(eras, config, protocol, gaps=gaps, atr_parity=parity)
    original = ROOT / ("goldnix/out/run_f8058f65db29/trades.csv" if args.study == "V1"
                       else "goldnix_v2/out/run_5f16e32256eb/trades.csv")
    expected = pd.read_csv(original, parse_dates=["entry_ts", "exit_ts"])
    pd.testing.assert_frame_equal(trades[["entry_ts", "exit_ts", "dir", "r_multiple"]].reset_index(drop=True),
                                  expected[["entry_ts", "exit_ts", "dir", "r_multiple"]], check_dtype=False,
                                  rtol=1e-10, atol=1e-10)
    result.update({"study": args.study, "strategy_trades_match_previous_run": True,
                   "data_sha256": hashes, "atr_evidence_sha256": hashlib.sha256(parity_path.read_bytes()).hexdigest()})
    trades.to_csv(output / "trades.csv", index=False)
    baseline.to_csv(output / "baseline_trades.csv.gz", index=False, compression="gzip")
    diagnostics.to_csv(output / "sampler_diagnostics.csv", index=False)
    draw_summary = baseline.groupby(["era", "draw", "dir"]).r_multiple.agg(["count", "mean"])
    draw_summary.to_csv(output / "baseline_draws.csv")
    dump_yaml(config, output / "config.yaml")
    dump_yaml(protocol, output / "protocol.yaml")
    (output / "metrics.json").write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n")
    lines = [f"# {args.study}: corrected Step 6", "", "Evaluation: COMPLETE", "",
             f"Verdict: **{result['verdict']}**", "", "| Gate | Pass | Value | Requirement |",
             "| --- | --- | --- | --- |"]
    for name, gate in result["gates"].items():
        lines.append(f"| {name} | {gate['passed']} | {gate['value']} | {gate['rule']} |")
    lines += ["", "Baseline: 200 independent seeded MCMC chains targeting uniform schedules",
              "conditioned on the same long/short counts, one-position rule and daily halt.",
              "Finite burn-in approximates this conditional distribution; see diagnostics.",
              f"Sampler warning: {result['sampler_has_warning']}.",
              "Signal/baseline confidence bounds use identical sampled calendar months.",
              "Previous strategy trades reproduced exactly. No holdout was read."]
    (output / "verdict.md").write_text("\n".join(lines) + "\n")
    if manifest != source_manifest(ROOT):
        raise RuntimeError("Sources changed during evaluation; refusing freeze")
    freeze_run(ROOT, output, verdict=result["verdict"], code_commit=commit,
               configs={"decision": config, "evaluation": protocol})
    if not verify_run(ROOT, output):
        raise RuntimeError("Freeze failed validation")
    print(json.dumps({"study": args.study, "output": str(output), "verdict": result["verdict"],
                       "freeze_valid": True}, indent=2), flush=True)


if __name__ == "__main__":
    main()
