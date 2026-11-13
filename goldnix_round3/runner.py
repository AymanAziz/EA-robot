"""Registered tight-stop screen at the verified one-ounce minimum exposure."""

import hashlib
import json
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from goldnix_research.screen import candidate_eras
from goldnix_round2.runner import evaluate_candidate
from goldnix_round3.feasibility import drawdown_lower_bound
from goldnix_step7.runner import preflight
from params.config import load_yaml


def _worker(root, candidate, protocol):
    root = Path(root)
    result, trades = evaluate_candidate(candidate_eras(root, candidate, protocol), candidate,
                                        load_yaml(root / "goldnix/params/decision.yaml"), protocol)
    # Round 2's conditional shortlist is inapplicable: this round requires G7
    # at the verified one-ounce exposure, with the same $20 equity and $2.40 limit.
    result["selected_for_full_evaluation"] = all(result[k] for k in
        ("G1", "G4", "G5", "G6", "G7_verified_exposure", "G8", "G9"))
    result["selection_exposure_oz"] = 1.
    pnl = trades.r_multiple.to_numpy() * np.maximum(trades.atr * candidate["stop_atr"], .5)
    result["loss_run_bound"] = drawdown_lower_bound(pnl, annual_trades=result["annual_trades"], limit_usd=2.4)
    return result, trades


def verify_previous(root):
    counts = {}
    for folder in ("goldnix_research", "goldnix_round2"):
        manifest = json.loads((root / folder / "out/MANIFEST.json").read_text())["file_sha256"]
        for name, expected in manifest.items():
            if hashlib.sha256((root / name).read_bytes()).hexdigest() != expected:
                raise PermissionError(f"Prior research changed: {name}")
        counts[folder] = len(manifest)
    return counts


def main():
    root = Path(__file__).resolve().parents[1]
    preflight(root)
    counts = verify_previous(root)
    directory = root / "goldnix_round3"
    protocol = json.loads((directory / "protocol.json").read_text())
    if protocol["holdout_access"] or protocol["new_trials"] != len(protocol["candidate_configs"]):
        raise ValueError("Invalid fixed experiment registry")
    if hashlib.sha256((root / protocol["data_path"]).read_bytes()).hexdigest() != protocol["data_sha256"]:
        raise PermissionError("Historical data hash mismatch")
    protocol["atr_parity_verified"] = "- Result: PASS" in (root / "goldnix/parity/ATR_PARITY_RESULT.md").read_text()
    output = directory / "out"
    output.mkdir(exist_ok=False)
    manifest = {}
    dependencies = [p for p in directory.rglob("*") if p.is_file() and p.suffix in {".py", ".json"}
                    and "out" not in p.parts and "venue" not in p.parts]
    for name in ("goldnix_round2/out/SUMMARY.json",):
        dependencies += [root / key for key in json.loads((root / name).read_text())["source_sha256"]]
    for path in set(dependencies):
        name = path.relative_to(root)
        data = path.read_bytes()
        snapshot = output / "source" / name
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        snapshot.write_bytes(data)
        manifest[name.as_posix()] = hashlib.sha256(data).hexdigest()
    (output / "STARTED.json").write_text(json.dumps({"started_utc": datetime.now(UTC).isoformat(),
        "source_sha256": manifest, "previous_files_verified": counts}, indent=2) + "\n")
    # Audit S11 without changing or resimulating its already recorded outcomes.
    reference = json.loads((root / "goldnix_round2/out/S11/metrics.json").read_text())
    trades = pd.read_csv(root / "goldnix_round2/out/S11/trades.csv")
    pnl = trades.r_multiple.to_numpy() * np.maximum(trades.atr * reference["candidate"]["stop_atr"], .5)
    bound = drawdown_lower_bound(pnl, annual_trades=reference["annual_trades"], limit_usd=2.4)
    (output / "S11_LOSS_RUN_BOUND.json").write_text(json.dumps(bound, indent=2) + "\n")
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
                "mean_r": result["bootstrap"]["mean_r"], "p99_usd_at_1oz": result["p99_usd_at_verified_1oz"],
                "fill_delta_pp": result["max_fill_delta_pp"],
                "qualifies": result["selected_for_full_evaluation"]}), flush=True)
    for name, expected in manifest.items():
        if hashlib.sha256((root / name).read_bytes()).hexdigest() != expected:
            raise PermissionError("Source changed during experiment")
    preflight(root)
    verify_previous(root)
    results.sort(key=lambda r: r["id"])
    qualified = [r for r in results if r["selected_for_full_evaluation"]]
    selected = max(qualified, key=lambda r: (r["bootstrap"]["selection_lower"], r["id"])) if qualified else None
    summary = {"status": "SCREEN_COMPLETE", "approval": False, "source_sha256": manifest,
        "completed_utc": datetime.now(UTC).isoformat(), "new_trials": len(results),
        "cumulative_trials": protocol["trial_count"], "holdout_access": False,
        "qualified": [r["id"] for r in qualified], "selected": selected["id"] if selected else None,
        "results": results}
    (output / "SUMMARY.json").write_text(json.dumps(summary, indent=2, sort_keys=True, allow_nan=False) + "\n")
    print(json.dumps({"qualified": summary["qualified"], "selected": summary["selected"], "approval": False}), flush=True)


if __name__ == "__main__":
    main()
