"""Run the frozen V1 and V2 holdout diagnostics together, once."""

import argparse
import hashlib
import json
import platform
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import numpy as np

from gates.freeze import assert_holdout_unlocked
from goldnix_step6.freeze import verify_run
from goldnix_step7.collapse import collapse_check
from goldnix_step7.data import read_holdout
from goldnix_v2.signal import apply_v2_confirmation
from ingest.gaps import find_gaps
from ingest.ingest import load_bars
from params.config import load_yaml
from sim.engine import prepare_bars, run_engine

STUDIES = {"V1": "V1_4b823fa2ca89", "V2": "V2_f8bd017f3802"}
DATA_NAME = "xauusd_h1_20030505_20251231_bid_ask.csv"
START = pd.Timestamp("2026-01-01T00:00:00Z")
END = pd.Timestamp("2026-10-01T00:00:00Z")


def _write_json(path, value):
    with Path(path).open("x", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write("\n")


def _runner_sources():
    directory = Path(__file__).resolve().parent
    return {p.relative_to(directory).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(directory.rglob("*"))
            if p.is_file() and p.suffix in {".py", ".md", ".yaml"}
            and "out" not in p.relative_to(directory).parts}


def preflight(root):
    """Authenticate both research freezes, statistics, and historical warm-up data."""
    root = Path(root)
    assert_holdout_unlocked(root / "goldnix")
    studies = {}
    for version, directory in STUDIES.items():
        run = root / "goldnix_step6/out" / directory
        if not (run / "FROZEN.yaml").is_file() or not verify_run(root, run):
            raise PermissionError(f"{version} freeze missing or hash mismatch")
        frozen = load_yaml(run / "FROZEN.yaml")
        config_path = root / ("goldnix/params/decision.yaml" if version == "V1" else "goldnix_v2/decision.yaml")
        if frozen["configs"]["decision"] != load_yaml(config_path):
            raise PermissionError(f"{version} freeze config differs from the hashed strategy config")
        metrics = json.loads((run / "metrics.json").read_text())
        for kind, digest in metrics["data_sha256"].items():
            path = root / "goldnix/data" / kind / DATA_NAME
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                raise PermissionError(f"{version} in-sample {kind} data hash mismatch")
        studies[version] = {"config": frozen["configs"]["decision"], "metrics": metrics,
                            "freeze_sha256": hashlib.sha256((run / "FROZEN.yaml").read_bytes()).hexdigest()}
    return studies


def run_once(root, holdout_path):
    """Verify the research freeze before any holdout access."""
    root, holdout_path = Path(root).resolve(), Path(holdout_path).resolve()
    studies = preflight(root)
    output = root / "goldnix_step7/out"
    output.mkdir(parents=True, exist_ok=True)
    attempt_path = output / "ATTEMPT.json"
    if attempt_path.exists():
        raise FileExistsError("Step 7 is run once; the existing attempt is consumed")
    if any((output / name).exists() for name in ("V1", "V2", "RESULT.json", "INPUT.json", "ERROR.json")):
        raise FileExistsError("Existing attempt artifacts found; refusing a repeat")
    if not holdout_path.is_file():
        raise FileNotFoundError(f"Holdout file missing (not consumed): {holdout_path}")
    attempt = {
        "started_utc": datetime.now(UTC).isoformat(), "status": "ACCESS_STARTED",
        "input_path": str(holdout_path), "start_inclusive": START.isoformat(),
        "end_exclusive": END.isoformat(),
        "freezes": {v: s["freeze_sha256"] for v, s in studies.items()},
        "step7_source_sha256": _runner_sources(),
        "data_source": "EV Trading Labs (https://evtradelabs.com/data)",
        "formula": "mean_hold >= mean_in - 2 * sqrt(SE_in**2 + SE_hold**2)",
        "normalisation": "No fitted normalisation or volume segmentation in either frozen decision config",
        "boundary_policy": "Indicators warmed from in-sample history; trade only holdout signals; start flat",
        "runtime": {"python": platform.python_version(), "numpy": np.__version__, "pandas": pd.__version__},
    }
    # Atomic exclusive creation happens before the first holdout read. Never delete it.
    _write_json(attempt_path, attempt)
    try:
        return _evaluate(root, holdout_path, studies, output, attempt)
    except BaseException as error:
        _write_json(output / "ERROR.json", {
            "status": "FAILED_AFTER_ACCESS", "holdout_consumed": True,
            "error_type": type(error).__name__, "error": str(error),
            "failed_utc": datetime.now(UTC).isoformat(),
        })
        raise


def _evaluate(root, holdout_path, studies, output, attempt):
    payload = holdout_path.read_bytes()
    snapshot_dir = root / "var/goldnix_step7_holdout"
    snapshot_dir.mkdir(parents=True, exist_ok=False)
    snapshot = snapshot_dir / ("source.json.gz" if payload.startswith(b"\x1f\x8b") else "source.data")
    with snapshot.open("xb") as handle:
        handle.write(payload)
    snapshot.chmod(0o444)
    input_record = {"sha256": hashlib.sha256(payload).hexdigest(), "bytes": len(payload),
                    "snapshot": snapshot.relative_to(root).as_posix()}
    _write_json(output / "INPUT.json", input_record)
    holdout = read_holdout(payload, start=START, end=END)
    history = load_bars(root / "goldnix/data/clean" / DATA_NAME)
    outcomes = {}
    for version, study in studies.items():
        config, metrics = study["config"], study["metrics"]
        warmup = config.get("warmup_h1_bars", load_yaml(root / "goldnix/data/eras.yaml")["warmup_bars"])
        frame = pd.concat([history.tail(warmup), holdout], ignore_index=True)
        frame["era"] = "HOLDOUT"
        frame = prepare_bars(frame, config)
        if version == "V2":
            frame = apply_v2_confirmation(
                frame, h4_period=config["h4_aroon_period"], ties=config["ties"],
                max_spread_atr=config["vol_ceiling_atr"], server_timezone=config["server_timezone"],
            )
        frame = frame.loc[frame.timestamp_utc.ge(START)].reset_index(drop=True)
        trades = run_engine(frame, config, gaps=find_gaps(frame)).trades
        outcome = collapse_check(trades.r_multiple, in_sample_mean=metrics["pooled"]["mean_r"],
                                 in_sample_se=metrics["pooled"]["bootstrap"]["standard_error"])
        outcome["step6_verdict"] = metrics["verdict"]
        outcome["warmup_bars"] = warmup
        outcome["end_of_data_exits"] = int(trades.exit_reason.eq("end_of_data").sum())
        outcome["step8_permitted"] = bool(
            metrics["verdict"] == "PASS" and outcome["verdict"] == "PASS"
            and all(metrics["gates"][f"G{i}"]["passed"] for i in range(1, 10))
        )
        study_output = output / version
        study_output.mkdir(exist_ok=False)
        trades.to_csv(study_output / "trades.csv", index=False)
        _write_json(study_output / "metrics.json", outcome)
        outcomes[version] = outcome
    preflight(root)
    if attempt["step7_source_sha256"] != _runner_sources():
        raise PermissionError("Step 7 source changed during the holdout attempt")
    result = {"status": "COMPLETE", "studies": outcomes,
              "completed_utc": datetime.now(UTC).isoformat(), "protocol": attempt,
              "input": input_record, "holdout_bars": len(holdout),
              "first_bar": holdout.timestamp_utc.min().isoformat(),
              "last_bar": holdout.timestamp_utc.max().isoformat()}
    lines = ["# Step 7: holdout collapse diagnostic", "",
             f"Window: {START.isoformat()} inclusive to {END.isoformat()} exclusive.",
             f"Input SHA-256: `{input_record['sha256']}`.", "",
             "| Study | Baskets | Mean R | SE holdout | Collapse threshold R | Verdict | Step 8 permitted |",
             "| --- | ---: | ---: | ---: | ---: | --- | --- |"]
    for version, outcome in outcomes.items():
        values = ["n/a" if outcome[key] is None else f"{outcome[key]:.6f}"
                  for key in ("holdout_mean_r", "holdout_se", "threshold_r")]
        lines.append(f"| {version} | {outcome['baskets']} | {' | '.join(values)} | "
                     f"{outcome['verdict']} | {outcome['step8_permitted']} |")
    lines += ["", "This checks collapse only; a PASS cannot establish an edge or repair Step 6 failures.",
              "A FAIL_DISCARD requires discarding the strategy without retuning on this holdout.",
              "Fewer than two baskets cannot yield a standard error or a PASS.",
              "Data source: [EV Trading Labs](https://evtradelabs.com/data).",
              "See RESULT.json for unrounded statistics, source hashes, and execution provenance."]
    with (output / "REPORT.md").open("x", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")
    result["artifact_sha256"] = {
        p.relative_to(output).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(output.rglob("*")) if p.is_file()
    }
    _write_json(output / "RESULT.json", result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--preflight", action="store_true", help="Verify freezes without reading holdout data")
    mode.add_argument("--holdout", type=Path, help="EV 2026 XAUUSD H1 native JSON/gzip or bid/ask CSV")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if args.preflight:
        studies = preflight(root)
        result = {
            "status": "FROZEN_INPUTS_VERIFIED", "holdout_read": False,
            "holdout_attempt_exists": (root / "goldnix_step7/out/ATTEMPT.json").exists(),
            "start_inclusive": START.isoformat(), "end_exclusive": END.isoformat(),
            "step7_source_sha256": _runner_sources(),
            "studies": {version: {"freeze_sha256": study["freeze_sha256"],
                                  "step6_verdict": study["metrics"]["verdict"],
                                  "in_sample_mean_r": study["metrics"]["pooled"]["mean_r"],
                                  "in_sample_se": study["metrics"]["pooled"]["bootstrap"]["standard_error"]}
                        for version, study in studies.items()},
        }
    else:
        result = run_once(root, args.holdout)
    print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
