"""Run the finite registered H01/H4/failure-exit comparison on four in-sample eras."""

from datetime import UTC, datetime
import json
from pathlib import Path
import shutil

import numpy as np
import pandas as pd

from goldnix_mtf.data import CACHE, ROOT, digest
from goldnix_mtf.evaluate import sampler_statistics, statistics
from goldnix_mtf2.replay import choose, material_gap
from goldnix_research.screen import candidate_eras, screen_statistics
from goldnix_round2.execution import Market as H1Market
from goldnix_round2.runner import execution_config, prepared_eras
from goldnix_step6.baseline import sample_schedules, schedule_is_valid
from goldnix_step6.bootstrap import paired_month_bootstrap
from ingest.gaps import find_gaps
from metrics.montecarlo import monte_carlo_drawdown
from params.config import load_yaml

from .method import FakeoutMarket

HERE = Path(__file__).resolve().parent
NAMES = ["H01", "COMMON_H01", "H02_H4", "H03_H4_FAKEOUT"]


def write(path, value):
    with path.open("x") as file:
        json.dump(value, file, indent=2, allow_nan=False)
        file.write("\n")


def run():
    plan = json.loads((HERE / "protocol.json").read_text())
    frozen = ROOT / "goldnix_mtf2/out/H01_S11_M5_REPLAY"
    original = json.loads((frozen / "RESULT.json").read_text())
    assert digest(frozen / "RESULT.json") == plan["base_result_sha256"]
    assert digest(ROOT / plan["gates_path"]) == plan["gates_sha256"]
    for relative, expected in json.loads((frozen / "FROZEN.json").read_text())["artifact_sha256"].items():
        if digest(frozen / relative) != expected:
            raise ValueError("Frozen H01 artifact changed: " + relative)
    for relative, expected in original["source_sha256"].items():
        if digest(ROOT / relative) != expected:
            raise ValueError("Frozen dependency changed: " + relative)
    data_manifest = json.loads((CACHE / "MANIFEST.json").read_text())
    if digest(CACHE / "validated.pkl") != data_manifest["validated_sha256"]:
        raise ValueError("M5 input changed")
    old_plan = json.loads((ROOT / "goldnix_round2/protocol.json").read_text())
    if digest(ROOT / old_plan["data_path"]) != old_plan["data_sha256"]:
        raise ValueError("H1 input changed")
    output = HERE / "out" / datetime.now(UTC).strftime("H02_%Y%m%dT%H%M%SZ")
    output.mkdir(parents=True, exist_ok=False)
    sources = {p.relative_to(ROOT).as_posix(): digest(p) for p in HERE.rglob("*")
               if p.is_file() and "out" not in p.parts and p.suffix in (".py", ".json")}
    for relative in sources:
        target = output / "SOURCE" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, target)
    write(output / "STARTED.json", {"started_utc": datetime.now(UTC).isoformat(), "plan": plan,
                                   "source_sha256": sources, "dependency_sha256": original["source_sha256"],
                                   "m5_data_sha256": data_manifest["validated_sha256"],
                                   "h1_data_sha256": old_plan["data_sha256"], "step7_payload_access": False})
    old_s11 = json.loads((ROOT / "goldnix_round2/out/full_evaluation/RESULT.json").read_text())
    candidate = old_s11["candidate"]
    config = execution_config(load_yaml(ROOT / "goldnix/params/decision.yaml"), candidate)
    raw_eras = candidate_eras(ROOT, candidate, old_plan)
    for frame in raw_eras.values():
        frame["channel_high"] = ((frame.bid_high + frame.ask_high) / 2).shift(1).rolling(20).max()
        frame["channel_low"] = ((frame.bid_low + frame.ask_low) / 2).shift(1).rolling(20).min()
    eras = prepared_eras(raw_eras, candidate)
    bars = pd.read_pickle(CACHE / "validated.pkl")
    if bars.timestamp_utc.max() >= pd.Timestamp("2026-01-01T00:00Z"):
        raise ValueError("Out-of-sample prices in input")
    market = FakeoutMarket(bars, {"atr": np.full(len(bars), np.nan), "ready": np.ones(len(bars), bool)},
                           {"usd_per_price_unit": .01})
    gaps = find_gaps(bars)
    boundaries = json.loads((ROOT / "goldnix_mtf/protocol.json").read_text())["eras_exclusive_end"]
    hold = {"reward_r": 3., "max_hold_minutes": 10**9}
    frames, reports = {name: [] for name in NAMES}, {name: {} for name in NAMES}
    pool_paths, initial_ids = {}, {}
    counts = {"eligible_h1_direction_opportunities": 0, "missing_exact_m5_entry": 0,
              "h4_not_ready": 0, "h4_disagrees_or_neutral": 0}
    for era, h1 in eras.items():
        entry_market = H1Market(h1)
        final = int(market.times.searchsorted(pd.Timestamp(boundaries[era][1])) - 1)
        signals = dict(enumerate(h1.signal.to_numpy()))
        rows, alternatives = {n: [] for n in NAMES}, {n: [] for n in NAMES}
        levels = {1: h1.channel_high.to_numpy(), -1: h1.channel_low.to_numpy()}

        def record(index, direction, distance, level, buffer, signal_index, guarded=False, policy="stop_first"):
            result = market.trade(index, direction, distance, hold, era, final, policy,
                                  fakeout=guarded, level=level, buffer=buffer)
            result["h1_signal_index"] = signal_index
            result["any_m5_gap"] = result["flags"] == "gap_risk"
            result["flags"] = "gap_risk" if material_gap(gaps, result["entry_ts"], result["exit_ts"]) else ""
            return result

        for direction in (1, -1):
            for i in range(len(h1) - 1):
                if not entry_market.eligible(i, direction, config):
                    continue
                counts["eligible_h1_direction_opportunities"] += 1
                stamp = entry_market.times[i + 1]
                index = int(market.times.searchsorted(stamp))
                if index >= final or market.times[index] != stamp:
                    counts["missing_exact_m5_entry"] += 1
                    continue
                atr = float(h1.atr.iloc[i])
                distance = max(2 * atr, .5)
                market.atr[index - 1] = atr
                level = float(levels[direction][i])
                buffer = max(float(entry_market.prices["ask_close"][i] - entry_market.prices["bid_close"][i]), .1 * atr)
                if not np.isfinite(level):
                    raise ValueError("Missing entry-known channel level")
                base = record(index, direction, distance, level, buffer, i)
                rows["H01"].append(base)
                actual_signal = signals[i] == direction
                if actual_signal:
                    alternatives["H01"].append(record(index, direction, distance, level, buffer, i, policy="target_first"))
                if not market.context["h4_ready"][index]:
                    counts["h4_not_ready"] += 1
                    continue
                rows["COMMON_H01"].append(base)
                if actual_signal:
                    alternatives["COMMON_H01"].append(alternatives["H01"][-1])
                if market.context["h4_direction"][index] != direction:
                    counts["h4_disagrees_or_neutral"] += 1
                    continue
                rows["H02_H4"].append(base)
                rows["H03_H4_FAKEOUT"].append(record(index, direction, distance, level, buffer, i, guarded=True))
                if actual_signal:
                    alternatives["H02_H4"].append(alternatives["H01"][-1])
                    alternatives["H03_H4_FAKEOUT"].append(record(index, direction, distance, level, buffer, i,
                                                               guarded=True, policy="target_first"))
        for name in NAMES:
            pool = pd.DataFrame(rows[name])
            selected, ids = choose(pool, signals, config["daily_halt_r"])
            optimistic, _ = choose(pd.DataFrame(alternatives[name]), signals, config["daily_halt_r"])
            if name == "H01":
                expected = pd.read_csv(frozen / f"{era}_trades.csv", parse_dates=["entry_ts", "exit_ts"], keep_default_na=False)
                pd.testing.assert_frame_equal(selected[expected.columns].reset_index(drop=True), expected,
                                              check_dtype=False, atol=1e-10, rtol=1e-10)
            selected.to_csv(output / f"{era}_{name}_trades.csv", index=False)
            pool_path = output / f"{era}_{name}_pool.pkl"
            pool.to_pickle(pool_path)
            pool_paths[(era, name)], initial_ids[(era, name)] = pool_path, ids
            frames[name].append(selected)
            delta = abs(selected.r_multiple.gt(0).mean() - optimistic.r_multiple.gt(0).mean()) * 100
            reports[name][era] = statistics(selected) | {"fill_delta_pp": float(delta),
                "failure_exits": int(selected.exit_reason.eq("fakeout_confirmed").sum()),
                "any_m5_gap_share": float(selected.any_m5_gap.mean())}
            print(json.dumps({"era": era, "candidate": name, **reports[name][era]}), flush=True)
        del rows, alternatives
    results = {}
    settings = plan["statistics"]
    years = (pd.Timestamp("2026-01-01T00:00Z") - pd.Timestamp("2005-06-01T00:00Z")).total_seconds() / (365.2425 * 86400)
    for name in NAMES:
        trades = pd.concat(frames[name], ignore_index=True)
        trades.to_csv(output / f"{name}_trades.csv", index=False)
        pooled = statistics(trades)
        boot = screen_statistics(trades, start="2005-06-01T00:00Z", end="2025-12-31T23:59:59Z",
                                 trials=plan["new_registered_minimum"], resamples=settings["bootstrap_resamples"],
                                 seed=settings["bootstrap_seed"])
        mc = monte_carlo_drawdown(trades.pnl_usd.to_numpy(), trades_per_year=max(1, round(len(trades) / years)),
                                  simulations=settings["monte_carlo_paths"], seed=settings["monte_carlo_seed"])
        checks = {"G1": boot["mean_lower"] > 0, "G4": sum(r["mean_r"] > 0 for r in reports[name].values()) >= 3,
                  "G5": len(trades) >= 1000, "G6": pooled["gap_risk_share"] <= .1,
                  "G7": mc.p99_max_drawdown_usd <= 2.4,
                  "G8": all(r["fill_delta_pp"] <= 8 for r in reports[name].values())}
        results[name] = {"pooled": pooled, "eras": reports[name], "bootstrap": boot,
                         "p99_drawdown_usd": mc.p99_max_drawdown_usd, "trades_per_year": mc.trades_per_year,
                         "preliminary_gates": {k: bool(v) for k, v in checks.items()},
                         "all_preliminary_passed": bool(all(checks.values())), "formal_step6_passed": False,
                         "G2": None, "G3": None, "G9_new_context_native_parity": "NOT_VERIFIED",
                         "step7_run": False, "deployed": False}
        if name in plan["candidates"] and all(checks.values()):
            baseline_frames, sampler_reports = [], {}
            for number, era in enumerate(eras):
                pool = pd.read_pickle(pool_paths[(era, name)])
                selected = frames[name][number]
                baseline, diagnostic = sample_schedules(pool, initial_ids=initial_ids[(era, name)],
                    draws=settings["baseline_draws"], sweeps=settings["baseline_sweeps"],
                    seed=settings["baseline_seed"] + number * 1000, daily_halt_r=config["daily_halt_r"])
                for _, draw in baseline.groupby("draw"):
                    assert schedule_is_valid(draw, daily_halt_r=config["daily_halt_r"])
                    assert draw.dir.value_counts().to_dict() == selected.dir.value_counts().to_dict()
                sampler_reports[era] = sampler_statistics(diagnostic, pool, selected,
                    {"sampler_retention_excess_warning": .05, "sampler_midpoint_difference_se_warning": 3.})
                baseline.to_csv(output / f"{era}_{name}_baseline.csv.gz", index=False, compression="gzip")
                baseline_frames.append(baseline)
            paired = paired_month_bootstrap(trades, pd.concat(baseline_frames, ignore_index=True),
                start="2005-06-01T00:00Z", end="2025-12-31T23:59:59Z", resamples=settings["bootstrap_resamples"],
                seed=settings["bootstrap_seed"])
            results[name].update(G2=paired["edge_point"] >= .1, G3=paired["edge_lower"] > 0,
                                 matched_bootstrap=paired, samplers=sampler_reports)
        print(json.dumps({"candidate": name, "pooled": pooled, "lower_r": boot["mean_lower"],
                          "p99_drawdown_usd": mc.p99_max_drawdown_usd, "checks": results[name]["preliminary_gates"]}), flush=True)
    for relative, expected in sources.items():
        if digest(ROOT / relative) != expected:
            raise ValueError("Research source changed during run")
    reference = results["H01"]
    for name in plan["candidates"]:
        current = results[name]
        current["comparison_vs_h01"] = {
            "mean_r_delta": current["pooled"]["mean_r"] - reference["pooled"]["mean_r"],
            "pnl_usd_delta": current["pooled"]["pnl_usd"] - reference["pooled"]["pnl_usd"],
            "drawdown_usd_delta": current["p99_drawdown_usd"] - reference["p99_drawdown_usd"],
            "trade_retention": current["pooled"]["trades"] / reference["pooled"]["trades"],
        }
    final = {"completed_utc": datetime.now(UTC).isoformat(), "status": "FINITE_SCREEN_COMPLETE",
             "counts": counts, "results": results, "h01_original_trades_reproduced": True,
             "formal_step6_passed": False, "step7_run": False, "active_demo": "P01_UNCHANGED",
             "limits": ["Reused public M5 history; not independent or target-broker tick validation",
                        "At least88 registered variants plus uncounted choices; preserve selection diagnostic",
                        "Future-price order inside M5 is unknown; stop-first and target-first retained",
                        "No qualified new-context native parity or matching untouched holdout"]}
    write(output / "RESULT.json", final)
    write(output / "MANIFEST.json", {"sha256": {p.relative_to(output).as_posix(): digest(p)
                                               for p in output.rglob("*") if p.is_file()}})
    print(json.dumps({"output": str(output), "status": final["status"], "step7_run": False}), flush=True)
    return output


if __name__ == "__main__":
    run()
