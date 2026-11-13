"""Unchanged S11 H1 decisions replayed on M5 quotes, with all original gates."""

import json
from datetime import UTC, datetime

import numpy as np
import pandas as pd

from gates.verdict import evaluate_gates
from goldnix_mtf.data import CACHE, ROOT, digest
from goldnix_mtf.evaluate import preserved_freezes, sampler_statistics, statistics
from goldnix_mtf2.evaluate import manifest, write_json
from goldnix_mtf2.method import Market as M5Market
from goldnix_research.screen import candidate_eras, screen_statistics
from goldnix_round2.execution import Market as H1Market, run_managed
from goldnix_round2.runner import execution_config, prepared_eras
from goldnix_step6.baseline import sample_schedules, schedule_is_valid
from goldnix_step6.bootstrap import paired_month_bootstrap
from ingest.gaps import find_gaps
from metrics.montecarlo import monte_carlo_drawdown
from params.config import load_yaml

DIRECTORY = ROOT / "goldnix_mtf2"


def material_gap(gaps, entry, exit_):
    if gaps.empty:
        return False
    start = pd.DatetimeIndex(gaps.gap_start).asi8
    end = pd.DatetimeIndex(gaps.gap_end).asi8
    i = int(np.searchsorted(start, pd.Timestamp(entry).value))
    return bool(i < len(start) and end[i] <= pd.Timestamp(exit_).value)


def choose(pool, signals, halt):
    selected, daily, last = [], {}, -1
    rows = pool.loc[pool.h1_signal_index.map(signals).eq(np.where(pool.dir.eq("BUY"), 1, -1))]
    for row in rows.sort_values("entry_index").itertuples():
        if row.entry_index <= last or daily.get(row.entry_day, 0.) <= halt:
            continue
        selected.append(row.Index)
        last = row.exit_index
        daily[row.exit_day] = daily.get(row.exit_day, 0.) + row.r_multiple
    return pool.loc[selected].copy(), selected


def main():
    protocol = json.loads((DIRECTORY / "replay_protocol.json").read_text())
    old = json.loads((ROOT / "goldnix_round2/out/full_evaluation/RESULT.json").read_text())
    old_protocol = json.loads((ROOT / "goldnix_round2/protocol.json").read_text())
    if digest(ROOT / "goldnix_round2/out/full_evaluation/RESULT.json") != protocol["historical_result_sha256"]:
        raise PermissionError("Reference result changed")
    for name, expected in old["source_sha256"].items():
        if digest(ROOT / name) != expected:
            raise PermissionError(f"Reference source changed: {name}")
    if digest(ROOT / old_protocol["data_path"]) != old_protocol["data_sha256"]:
        raise PermissionError("H1 data changed")
    if digest(ROOT / "goldnix/gates/rules.yaml") != protocol["gates_sha256"]:
        raise PermissionError("Gate thresholds changed")
    data = json.loads((CACHE / "MANIFEST.json").read_text())
    if digest(CACHE / "validated.pkl") != data["validated_sha256"]:
        raise PermissionError("M5 data changed")
    preserved_freezes()
    sources = manifest()
    output = DIRECTORY / "out/H01_S11_M5_REPLAY"
    output.mkdir(exist_ok=False)
    write_json(output / "STARTED.json", {"started_utc": datetime.now(UTC).isoformat(), "protocol": protocol,
        "source_sha256": sources, "m5_data_sha256": data["validated_sha256"]})
    for name, expected in sources.items():
        target = output / "source" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / name).read_bytes())
        if digest(target) != expected:
            raise PermissionError("Snapshot mismatch")
    candidate = old["candidate"]
    config = execution_config(load_yaml(ROOT / "goldnix/params/decision.yaml"), candidate)
    eras = prepared_eras(candidate_eras(ROOT, candidate, old_protocol), candidate)
    reproduced = pd.concat([run_managed(frame, config, gaps=find_gaps(frame)) for frame in eras.values()], ignore_index=True)
    original = pd.read_csv(ROOT / "goldnix_round2/out/S11/trades.csv", parse_dates=["entry_ts", "exit_ts"], keep_default_na=False)
    pd.testing.assert_frame_equal(reproduced, original, check_dtype=False, atol=1e-10, rtol=1e-10)
    write_json(output / "ORIGINAL_REPRODUCED.json", {"trades": len(original), "all_columns_match": True})
    print("Original S11 reproduces all 1,025 trades before changing execution resolution", flush=True)
    bars = pd.read_pickle(CACHE / "validated.pkl")
    m5 = M5Market(bars, {"atr": np.full(len(bars), np.nan), "ready": np.ones(len(bars), bool)}, protocol)
    material_gaps = find_gaps(bars)
    hold = {"reward_r": 3., "max_hold_minutes": 10**9}
    bounds = json.loads((ROOT / "goldnix_mtf/protocol.json").read_text())["eras_exclusive_end"]
    frames, baseline_frames, reports, samplers, quotes = [], [], {}, {}, {}
    for number, (era, h1bars) in enumerate(eras.items()):
        native_h1 = H1Market(h1bars)
        last = int(m5.times.searchsorted(pd.Timestamp(bounds[era][1])) - 1)
        rows, alternative_rows, missing, diffs = [], [], 0, []
        signal_map = dict(enumerate(h1bars.signal.to_numpy()))
        for direction in (1, -1):
            for i in range(len(h1bars) - 1):
                if not native_h1.eligible(i, direction, config):
                    continue
                stamp = native_h1.times[i + 1]
                entry = int(m5.times.searchsorted(stamp))
                if entry >= last or m5.times[entry] != stamp:
                    missing += 1
                    continue
                atr = float(h1bars.atr.iloc[i])
                distance = max(2 * atr, .5)
                m5.atr[entry - 1] = atr
                diffs.append(max(abs(m5.p[f"{side}_open"][entry] - native_h1.prices[f"{side}_open"][i + 1]) for side in ("bid", "ask")))
                record = m5.trade(entry, direction, distance, hold, era, last)
                record["h1_signal_index"] = i
                record["any_m5_gap"] = record["flags"] == "gap_risk"
                record["flags"] = "gap_risk" if material_gap(material_gaps, record["entry_ts"], record["exit_ts"]) else ""
                rows.append(record)
                if signal_map[i] == direction:
                    alternate = m5.trade(entry, direction, distance, hold, era, last, "target_first")
                    alternate["h1_signal_index"] = i
                    alternative_rows.append(alternate)
        pool = pd.DataFrame(rows)
        trades, initial = choose(pool, signal_map, config["daily_halt_r"])
        optimistic, _ = choose(pd.DataFrame(alternative_rows), signal_map, config["daily_halt_r"])
        trades.to_csv(output / f"{era}_trades.csv", index=False)
        frames.append(trades)
        reports[era] = {**statistics(trades), "any_m5_gap_share": float(trades.any_m5_gap.mean()),
                       "fill_delta_pp": float(abs(trades.r_multiple.gt(0).mean() - optimistic.r_multiple.gt(0).mean()) * 100)}
        quotes[era] = {"eligible_direction_entries_missing_exact_m5_quote": missing,
                       "max_h1_m5_entry_quote_difference": float(max(diffs)), "matched_direction_entries": len(diffs)}
        print(f"{era}: {len(trades)} trades, mean {trades.r_multiple.mean():.5f}R; matching baseline", flush=True)
        baseline, diagnostics = sample_schedules(pool, initial_ids=initial,
            draws=protocol["baseline_draws"], sweeps=protocol["baseline_sweeps"],
            seed=protocol["baseline_seed"] + number * 1000, daily_halt_r=config["daily_halt_r"])
        for _, draw in baseline.groupby("draw"):
            if not schedule_is_valid(draw, daily_halt_r=config["daily_halt_r"]):
                raise AssertionError("Invalid baseline execution envelope")
            if draw.dir.value_counts().to_dict() != trades.dir.value_counts().to_dict():
                raise AssertionError("Direction quotas changed")
        samplers[era] = sampler_statistics(diagnostics, pool, trades, protocol)
        baseline.to_csv(output / f"{era}_baseline.csv.gz", index=False, compression="gzip")
        diagnostics.to_csv(output / f"{era}_diagnostics.csv", index=False)
        baseline_frames.append(baseline)
        print(f"{era}: 200 matched baseline schedules validated", flush=True)
    trades = pd.concat(frames, ignore_index=True)
    baseline = pd.concat(baseline_frames, ignore_index=True)
    trades.to_csv(output / "trades.csv", index=False)
    boot = paired_month_bootstrap(trades, baseline, start="2005-06-01T00:00Z", end="2025-12-31T23:59:59Z",
        resamples=protocol["bootstrap_resamples"], seed=protocol["bootstrap_seed"])
    search = screen_statistics(trades, start="2005-06-01T00:00Z", end="2025-12-31T23:59:59Z",
        trials=protocol["cumulative_registered_variants"], resamples=protocol["bootstrap_resamples"], seed=protocol["bootstrap_seed"])
    years = (pd.Timestamp("2026-01-01T00:00Z") - pd.Timestamp("2005-06-01T00:00Z")).total_seconds() / (365.2425 * 86400)
    risk = monte_carlo_drawdown(trades.pnl_usd.to_numpy(), trades_per_year=max(1, round(len(trades) / years)),
        simulations=protocol["monte_carlo_paths"], seed=protocol["monte_carlo_seed"])
    pooled = statistics(trades)
    inputs = {"account_usd": 20., "bootstrap_lower_bound": boot["mean_lower"],
        "signal_minus_baseline": boot["edge_point"], "edge_lower_bound": boot["edge_lower"],
        "positive_eras": sum(r["mean_r"] > 0 for r in reports.values()), "baskets": len(trades),
        "gap_risk_share": pooled["gap_risk_share"], "mc_p99_drawdown_usd": risk.p99_max_drawdown_usd,
        "max_fill_delta_pp": max(r["fill_delta_pp"] for r in reports.values()), "atr_parity": True}
    verdict = evaluate_gates(inputs, load_yaml(ROOT / "goldnix/gates/rules.yaml"))
    result = {"candidate_id": protocol["candidate_id"], "raw_gate_verdict": verdict.verdict,
        "evaluation_complete": True, "gates": verdict.gates, "gate_inputs": inputs,
        "pooled": pooled, "eras": reports, "quote_comparison": quotes, "bootstrap": boot,
        "selection_diagnostic": search, "cumulative_registered_trials": protocol["cumulative_registered_variants"],
        "samplers": samplers, "sampler_has_warning": any(v["mixing_warning"] for v in samplers.values()),
        "monte_carlo": {"paths": risk.simulations, "p99_drawdown_usd": risk.p99_max_drawdown_usd,
                        "trades_per_year": risk.trades_per_year},
        "by_direction": {d: statistics(trades.loc[trades.dir.eq(d)]) for d in ("BUY", "SELL")},
        "extra_cost_fixed_schedule": {str(x): float((trades.r_multiple - x).mean()) for x in (.1, .25)},
        "approval": False, "holdout_performance_access": False,
        "limitation": "Separate H1 channel strategy; not success of U01/MTF retest method. More detailed public M5 execution still is not target-venue historical tick/fee or independent validation. Material-gap definition retained from original Step6; all shorter M5 gaps separately reported.",
        "completed_utc": datetime.now(UTC).isoformat(), "source_sha256": sources}
    preserved_freezes()
    if manifest() != sources:
        raise PermissionError("Replay source changed during evaluation")
    write_json(output / "RESULT.json", result)
    write_json(output / "FROZEN.json", {"completed_utc": result["completed_utc"], "approval": False,
        "artifact_sha256": {p.relative_to(output).as_posix(): digest(p) for p in output.rglob("*") if p.is_file()}})
    print(json.dumps({"status": verdict.verdict, "pooled": pooled, "gates": verdict.gates,
                     "selection_lower": search["selection_lower"]}), flush=True)


if __name__ == "__main__":
    main()
