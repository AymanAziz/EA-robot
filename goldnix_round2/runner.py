"""Run a fixed second-round registry, including unchanged gates and explicit exposure scenarios."""

import hashlib
import json
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from goldnix_research.candidates import prepare_candidate
from goldnix_research.screen import candidate_eras, screen_statistics
from goldnix_round2.candidates import prepare_round2
from goldnix_round2.execution import run_managed
from goldnix_step7.runner import preflight
from ingest.gaps import find_gaps
from metrics.montecarlo import monte_carlo_drawdown
from params.config import load_yaml


def execution_config(base, candidate):
    return {**base, "stop_atr": candidate["stop_atr"],
            "target_atr": candidate["stop_atr"] * candidate["reward_ratio"],
            "exit_management": candidate["exit_management"]}


def prepared_eras(eras, candidate):
    prepared = {}
    for name, raw in eras.items():
        frame = prepare_round2(raw, candidate)
        start = raw.attrs.get("trade_start", raw.timestamp_utc.min())
        prepared[name] = frame.loc[frame.timestamp_utc.ge(start)].reset_index(drop=True)
    return prepared


def evaluate_candidate(eras, candidate, base_config, protocol):
    config = execution_config(base_config, candidate)
    frames, reports, starts, ends = [], {}, [], []
    for name, frame in prepared_eras(eras, candidate).items():
        gaps = find_gaps(frame)
        trades = run_managed(frame, config, gaps=gaps)
        alternate = run_managed(frame, {**config, "fill_policy": "target_first"}, gaps=gaps)
        delta = (100 * abs(float(trades.r_multiple.gt(0).mean()) - float(alternate.r_multiple.gt(0).mean()))
                 if len(trades) and len(alternate) else None)
        reports[name] = {"baskets": len(trades), "mean_r": float(trades.r_multiple.mean()) if len(trades) else None,
                         "fill_delta_pp": delta}
        frames.append(trades)
        starts.append(frame.timestamp_utc.min())
        ends.append(frame.timestamp_utc.max())
    trades = pd.concat(frames, ignore_index=True)
    stats = (screen_statistics(trades, start=min(starts), end=max(ends), trials=protocol["trial_count"],
                               resamples=protocol["bootstrap_resamples"], seed=protocol["bootstrap_seed"])
             if len(trades) else {"mean_r": None, "mean_lower": None, "selection_lower": None})
    years = ((max(ends) - min(starts)).total_seconds() + 3600) / (365.2425 * 86400)
    annual = max(1, round(len(trades) / years))
    risk = None
    if len(trades):
        distance = np.maximum(trades.atr.to_numpy() * config["stop_atr"], config["min_distance_usd"])
        risk = monte_carlo_drawdown(trades.r_multiple.to_numpy() * distance, trades_per_year=annual,
                                   simulations=protocol["monte_carlo_paths"], seed=protocol["monte_carlo_seed"])
    positive = sum(r["mean_r"] is not None and r["mean_r"] > 0 for r in reports.values())
    gaps = float(trades["flags"].eq("gap_risk").mean()) if len(trades) else None
    deltas = [r["fill_delta_pp"] for r in reports.values()]
    maximum = max(deltas) if all(d is not None for d in deltas) else None
    actual = risk.p99_max_drawdown_usd if risk else None
    conditional = actual * .01 if risk else None
    gates = {"G1": stats["mean_lower"] is not None and stats["mean_lower"] > 0,
             "G4": positive >= 3, "G5": len(trades) >= 1000,
             "G6": gaps is not None and gaps <= .10,
             "G7_verified_exposure": actual is not None and actual <= 2.4,
             "G7_product_scenario": conditional is not None and conditional <= 2.4,
             "G8": maximum is not None and maximum <= 8,
             "G9": bool(protocol.get("atr_parity_verified", False))}
    selected = all(gates[k] for k in ("G1", "G4", "G5", "G6", "G7_product_scenario", "G8", "G9"))
    return {"id": candidate["id"], "candidate": candidate, "baskets": len(trades), "eras": reports,
            "bootstrap": stats, "positive_eras": positive, "gap_risk_share": gaps,
            "max_fill_delta_pp": maximum, "annual_trades": annual,
            "monte_carlo_paths": protocol["monte_carlo_paths"],
            "p99_usd_at_verified_1oz": actual, "p99_usd_at_product_scenario_0_01oz": conditional,
            **gates, "selected_for_full_evaluation": selected, "approval": False,
            "account_verified": False, "unevaluated_gates": ["G2", "G3"]}, trades


def _worker(root, candidate, protocol):
    root = Path(root)
    return evaluate_candidate(candidate_eras(root, candidate, protocol), candidate,
                              load_yaml(root / "goldnix/params/decision.yaml"), protocol)


def _control(root, protocol, output):
    controls = [
        ({"family": "aroon", "period": 70, "threshold": 50, "stop_atr": 1,
          "reward_ratio": 2, "warmup_bars": 100, "exit_management": "fixed"},
         "goldnix_step6/out/V1_4b823fa2ca89/trades.csv"),
        ({"family": "channel", "period": 20, "stop_atr": 2, "reward_ratio": 3,
          "warmup_bars": 100, "exit_management": "fixed"},
         "goldnix_research/out/screen/C20/trades.csv"),
    ]
    results = []
    for candidate, reference in controls:
        frames = []
        for _, raw in candidate_eras(root, candidate, protocol).items():
            prepared = prepare_candidate(raw, candidate)
            prepared = prepared.loc[prepared.timestamp_utc.ge(raw.attrs["trade_start"])].reset_index(drop=True)
            frames.append(run_managed(prepared, execution_config(load_yaml(root / "goldnix/params/decision.yaml"),
                                                                candidate), gaps=find_gaps(prepared)))
        actual = pd.concat(frames, ignore_index=True)
        expected = pd.read_csv(root / reference, parse_dates=["entry_ts", "exit_ts"], keep_default_na=False)
        pd.testing.assert_frame_equal(actual, expected, check_dtype=False, atol=1e-10, rtol=1e-10)
        results.append({"reference": reference, "baskets": len(actual), "all_columns_match": True})
    (output / "CONTROLS.json").write_text(json.dumps(results, indent=2) + "\n")
    print("Historical controls: V1 and C20 reproduce every trade column", flush=True)


def main():
    root = Path(__file__).resolve().parents[1]
    preflight(root)
    directory = root / "goldnix_round2"
    protocol = json.loads((directory / "protocol.json").read_text())
    if protocol["holdout_access"] or protocol["new_trials"] != len(protocol["candidate_configs"]):
        raise ValueError("Invalid fixed experiment registry")
    data_path = root / protocol["data_path"]
    if hashlib.sha256(data_path.read_bytes()).hexdigest() != protocol["data_sha256"]:
        raise PermissionError("Historical data hash mismatch")
    protocol["atr_parity_verified"] = "- Result: PASS" in (root / "goldnix/parity/ATR_PARITY_RESULT.md").read_text()
    output = directory / "out"
    output.mkdir(exist_ok=False)
    (output / "source").mkdir()
    manifest = {}
    paths = [p for p in directory.rglob("*") if p.is_file() and p.suffix in {".py", ".json"} and "out" not in p.parts]
    paths += [root / "goldnix_research" / name for name in ("candidates.py", "screen.py", "risk_budget.py")]
    for path in paths:
        relative = path.relative_to(root)
        snapshot = output / "source" / relative
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        snapshot.write_bytes(path.read_bytes())
        manifest[relative.as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    (output / "STARTED.json").write_text(json.dumps({"started_utc": datetime.now(UTC).isoformat(),
                                                     "source_sha256": manifest}, indent=2) + "\n")
    _control(root, protocol, output)
    results = []
    with ProcessPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(_worker, str(root), c, protocol) for c in protocol["candidate_configs"]]
        for future in as_completed(futures):
            result, trades = future.result()
            run = output / result["id"]
            run.mkdir()
            trades.to_csv(run / "trades.csv", index=False)
            (run / "metrics.json").write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n")
            results.append(result)
            print(json.dumps({"id": result["id"], "baskets": result["baskets"],
                              "mean_r": result["bootstrap"]["mean_r"], "lower": result["bootstrap"]["mean_lower"],
                              "positive_eras": result["positive_eras"],
                              "scenario_p99_usd": result["p99_usd_at_product_scenario_0_01oz"],
                              "max_fill_delta_pp": result["max_fill_delta_pp"],
                              "qualifies": result["selected_for_full_evaluation"]}), flush=True)
    for name, digest in manifest.items():
        if hashlib.sha256((root / name).read_bytes()).hexdigest() != digest:
            raise PermissionError("Source changed during this experiment")
    preflight(root)
    results.sort(key=lambda r: r["id"])
    qualified = [r for r in results if r["selected_for_full_evaluation"]]
    selected = max(qualified, key=lambda r: (r["bootstrap"]["selection_lower"], r["id"])) if qualified else None
    summary = {"status": "SCREEN_COMPLETE", "approval": False, "account_verified": False,
               "completed_utc": datetime.now(UTC).isoformat(), "source_sha256": manifest,
               "new_trials": len(results), "cumulative_trials": protocol["trial_count"],
               "qualified": [r["id"] for r in qualified], "selected": selected["id"] if selected else None,
               "results": results}
    (output / "SUMMARY.json").write_text(json.dumps(summary, indent=2, sort_keys=True, allow_nan=False) + "\n")
    print(json.dumps({"qualified": summary["qualified"], "selected": summary["selected"]}), flush=True)


if __name__ == "__main__":
    main()
