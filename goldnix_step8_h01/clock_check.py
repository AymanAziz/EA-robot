"""Validate a bounded historical server offset against an independent UTC feed."""

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


def compare(native, independent, rules):
    reference = independent[["epoch_seconds", "bid_close"]].copy()
    reference["reference_return"] = np.log(reference.bid_close).diff().where(reference.epoch_seconds.diff().eq(3600))
    reference = reference.rename(columns={"bid_close": "reference_close"})
    reports, weekly = {}, {}
    for offset in rules["offsets_hours"]:
        frame = native.copy()
        frame["epoch_seconds"] = frame.server_epoch-offset*3600
        frame["broker_return"] = np.log(frame.bid_close).diff().where(frame.server_epoch.diff().eq(3600))
        match = frame.merge(reference, on="epoch_seconds", how="inner", validate="one_to_one").dropna()
        match["week"] = pd.to_datetime(match.epoch_seconds, unit="s", utc=True).dt.strftime("%G-W%V")
        reports[str(offset)] = {"pairs": len(match), "return_correlation": float(match.broker_return.corr(match.reference_return)),
            "median_absolute_close_difference": float((match.bid_close-match.reference_close).abs().median())}
        weekly[str(offset)] = {week: {"pairs": len(group),
            "return_correlation": float(group.broker_return.corr(group.reference_return)),
            "median_absolute_close_difference": float((group.bid_close-group.reference_close).abs().median())}
            for week, group in match.groupby("week")}
    ranked = sorted(reports, key=lambda k: reports[k]["return_correlation"], reverse=True)
    best, runner_up = ranked[:2]
    selected = reports[best]
    passed = selected["return_correlation"] >= rules["return_correlation_min"]
    passed &= selected["return_correlation"]-reports[runner_up]["return_correlation"] >= rules["correlation_margin_min"]
    passed &= selected["median_absolute_close_difference"] <= rules["median_absolute_bid_close_difference_max"]
    for week, result in weekly[best].items():
        alternatives = [weekly[k][week]["return_correlation"] for k in ranked[1:] if week in weekly[k]]
        passed &= (result["pairs"] >= rules["weekly_minimum_pairs"]
            and result["return_correlation"] >= rules["return_correlation_min"]
            and result["return_correlation"]-max(alternatives) >= rules["correlation_margin_min"]
            and result["median_absolute_close_difference"] <= rules["median_absolute_bid_close_difference_max"])
    return {"passed": bool(passed), "selected_offset_seconds": int(best)*3600,
        "pooled": reports, "weekly": weekly, "rules": rules,
        "scope": "Empirical price-clock alignment for Jan22-Feb29 2024 only; not a published broker DST policy"}


def main():
    output = Path(json.loads((HERE / "PROBE_LATEST.json").read_text())["output"])
    protocol = json.loads((output / "STARTED.json").read_text())
    source = ROOT / "goldnix/data/clean/xauusd_h1_20030505_20251231_bid_ask.csv"
    native = pd.read_csv(output / "h1.csv")
    independent = pd.read_csv(source, usecols=["epoch_seconds", "bid_close"])
    result = compare(native, independent, protocol["clock_validation_registered_before_comparison"])
    result["native_h1_sha256"] = hashlib.sha256((output / "h1.csv").read_bytes()).hexdigest()
    result["independent_utc_h1_sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
    (output / "CLOCK_CHECK.json").write_text(json.dumps(result, indent=2, allow_nan=False)+"\n")
    print(json.dumps({k: result[k] for k in ("passed", "selected_offset_seconds", "pooled")}, indent=2))


if __name__ == "__main__":
    main()
