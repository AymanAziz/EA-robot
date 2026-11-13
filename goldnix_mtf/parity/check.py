"""Compare native indicators and closed-bar mappings; never evaluate recent returns."""

import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from goldnix_mtf.data import digest
from goldnix_mtf.method import aggregate, available_rows, ema
from params.atr import atr_simple

DIRECTORY = Path(__file__).resolve().parent


def check(directory):
    directory = Path(directory)
    protocol = json.loads((DIRECTORY / "PROTOCOL.json").read_text())
    for name in ("PROTOCOL.json", "ExportM5Parity.mq5"):
        if digest(directory / "SOURCE" / name) != digest(DIRECTORY / name):
            raise PermissionError("Parity source differs from the executed snapshot")
    meta_frame = pd.read_csv(directory / "meta.csv")
    meta = dict(zip(meta_frame.key, meta_frame.value))
    checks = {}
    checks["identity_and_read_only"] = (all(int(meta[k]) == 1 for k in
        ("identity_matches_expected", "h1_complete", "m15_complete", "m5_complete"))
        and all(int(meta[k]) == 0 for k in ("terminal_trade_allowed", "script_trade_allowed", "positions", "orders")))
    frames = {label: pd.read_csv(directory / f"{label}.csv") for label in ("M5", "M15", "H1")}
    tolerance = protocol["strict_price_tolerance"]
    differences = {}
    for label, frame in frames.items():
        checks[f"{label}_rows"] = len(frame) == protocol["rows_each"] and frame["compare"].sum() == protocol["compare_rows"]
        checks[f"{label}_ordered"] = bool(np.all(np.diff(frame.server_epoch) > 0))
        checks[f"{label}_finite"] = bool(np.isfinite(frame[["open", "high", "low", "close", "indicator"]]).all().all())
        values = (atr_simple(frame.high, frame.low, frame.close, 14) if label == "M5"
                  else ema(frame.close, 50 if label == "H1" else 20))
        selected = frame["compare"].eq(1).to_numpy()
        delta = float(np.max(np.abs(values[selected] - frame.indicator.to_numpy()[selected])))
        differences[label] = delta
        checks[f"{label}_indicator"] = delta < tolerance
    m5 = frames["M5"]
    final = m5.loc[m5["compare"].eq(1)]
    availability = {}
    for label, seconds in (("H1", 3600), ("M15", 900)):
        higher = frames[label]
        # Same server clock on both sides; no historical timezone assumption.
        table = pd.DataFrame({"available_at": pd.to_datetime(higher.server_epoch + seconds, unit="s", utc=True)})
        decisions = pd.to_datetime(final.server_epoch + 300, unit="s", utc=True)
        indices = available_rows(decisions, table)
        if np.any(indices < 0):
            raise ValueError("Missing native history for availability comparison")
        expected = higher.server_epoch.to_numpy()[indices]
        actual = final[f"last_completed_{label.lower()}_open"].to_numpy()
        mismatches = int(np.sum(expected != actual))
        availability[label] = {"comparisons": len(final), "mismatches": mismatches}
        checks[f"{label}_closed_availability"] = mismatches == 0 and len(final) == protocol["m5_availability_comparisons"]
    # The recent comparison span uses a checked whole-hour offset; older export
    # rows crossing DST are not interpreted as a historical UTC conversion rule.
    observed_offset = int(meta["observed_server_offset_seconds"])
    offset = round(observed_offset / 3600) * 3600
    checks["recent_whole_hour_offset"] = abs(observed_offset - offset) <= 10
    lower = pd.DataFrame({"timestamp_utc": pd.to_datetime(m5.server_epoch - offset, unit="s", utc=True)})
    for side in ("bid", "ask"):
        for column in ("open", "high", "low", "close"):
            # Ask is a dummy copy solely to exercise the OHLC aggregator; no
            # spread/execution claim or trade is derived from these parity rows.
            lower[f"{side}_{column}"] = m5[column].to_numpy()
    aggregation = {}
    for label, minutes in (("H1", 60), ("M15", 15)):
        grouped = aggregate(lower, minutes)
        minimum = pd.to_datetime(int(final.server_epoch.min()) - offset, unit="s", utc=True)
        grouped = grouped.loc[grouped.timestamp_utc.ge(minimum)]
        native = frames[label].copy()
        native["timestamp_utc"] = pd.to_datetime(native.server_epoch - offset, unit="s", utc=True)
        matched = grouped.merge(native, on="timestamp_utc", validate="one_to_one")
        error = max(float(np.abs(matched[f"bid_{c}"] - matched[c]).max()) for c in ("open", "high", "low", "close"))
        aggregation[label] = {"complete_bars": len(matched), "max_abs_ohlc_error": error}
        checks[f"{label}_aggregation"] = (len(matched) >= protocol["minimum_complete_m5_aggregates"][label]
                                          and len(matched) == len(grouped) and error < tolerance)
    checks = {name: bool(value) for name, value in checks.items()}
    result = {"completed_utc": datetime.now(UTC).isoformat(), "passed": all(checks.values()), "checks": checks,
              "max_abs_indicator_difference": differences, "strict_tolerance": tolerance,
              "availability": availability, "aggregation": aggregation,
              "account_identity_matches": bool(int(meta["identity_matches_expected"])),
              "positions": int(meta["positions"]), "orders": int(meta["orders"]),
              "automation_enabled": bool(int(meta["terminal_trade_allowed"])), "strategy_performance_evaluated": False,
              "scope": "New M5 ATR14 plus H1/M15 EMA and closed-timeframe availability parity; not execution, spread, historical timezone or profitability validation",
              "source_sha256": {str(p.relative_to(DIRECTORY)): digest(p) for p in
                                  (DIRECTORY / "ExportM5Parity.mq5", DIRECTORY / "PROTOCOL.json", Path(__file__))},
              "input_sha256": {p.relative_to(directory).as_posix(): digest(p) for p in
                               [*directory.glob("*.csv"), * (directory / "SOURCE").iterdir()]}}
    payload = json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n"
    with (directory / "RESULT.json").open("x") as handle:
        handle.write(payload)
    print(json.dumps(result, indent=2))
    if not result["passed"]:
        raise AssertionError("Native parity checks failed")
    return result


if __name__ == "__main__":
    check(json.loads((DIRECTORY / "LATEST.json").read_text())["directory"])
