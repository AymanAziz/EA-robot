"""Compare actual tester deals to frozen H01 logic on the exported broker quotes."""

import hashlib
import json
import re
import shutil
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from goldnix_mtf2.method import Market as M5Market
from goldnix_research.candidates import prepare_candidate
from goldnix_research.risk_budget import apply_risk_budget
from goldnix_round2.execution import Market as H1Market
from goldnix_step8_h01.audit_receipt import audit
from goldnix_venue.demo_session import Terminal
from params.config import load_yaml

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
TICK_DTYPE = np.dtype([("server_msc", "<i8"), ("bid", "<f8"), ("ask", "<f8")])


def quote_bars(ticks, seconds, offset):
    """Aggregate each quote side separately before taking midpoint extrema."""
    frame = pd.DataFrame(ticks)
    frame["bucket"] = (frame.server_msc // 1000 - offset) // seconds * seconds
    grouped = frame.groupby("bucket", sort=True)
    bars = pd.concat([grouped[side].agg(["first", "max", "min", "last"]).rename(
        columns=dict(zip(("first", "max", "min", "last"),
                         (f"{side}_open", f"{side}_high", f"{side}_low", f"{side}_close"))))
        for side in ("bid", "ask")], axis=1).reset_index(names="epoch_seconds")
    bars["timestamp_utc"] = pd.to_datetime(bars.epoch_seconds, unit="s", utc=True)
    return bars


def reference(ticks, decision):
    parameters = decision["inputs"]
    operation = decision["operational_inputs"]
    h1 = quote_bars(ticks, 3600, operation["ServerOffsetSeconds"])
    m5 = quote_bars(ticks, 300, operation["ServerOffsetSeconds"])
    h1["era"] = "broker_parity"
    candidate = {"family": "channel", "period": parameters["ChannelPeriod"]}
    raw = prepare_candidate(h1, candidate)
    prepared = apply_risk_budget(raw, stop_atr=parameters["StopATR"],
        account_usd=parameters["ReferenceAccountUSD"], risk_share=parameters["RiskShare"],
        usd_per_price_unit=parameters["USDPerPriceUnit"])
    config = {**load_yaml(ROOT / "goldnix/params/decision.yaml"), "stop_atr": parameters["StopATR"],
              "target_atr": parameters["StopATR"] * parameters["TargetR"]}
    market = H1Market(prepared)
    engine = M5Market(m5, {"atr": np.full(len(m5), np.nan), "ready": np.ones(len(m5), bool)},
                      {"usd_per_price_unit": parameters["USDPerPriceUnit"]})
    start = pd.Timestamp(datetime.strptime(operation["TradeFromUTC"], "%Y.%m.%d %H:%M:%S"), tz="UTC")
    records, daily, last = [], {}, -1
    for i in range(parameters["WarmupBars"] - 1, len(h1) - 1):
        stamp = market.times[i + 1]
        d = int(prepared.signal.iloc[i])
        if stamp < start or d == 0 or not market.eligible(i, d, config):
            continue
        entry = int(engine.times.searchsorted(stamp))
        if entry >= len(m5)-1 or engine.times[entry] != stamp or entry <= last:
            continue
        if daily.get(stamp.value // (86400 * 10**9), 0) <= -parameters["DailyHaltR"]:
            continue
        atr = float(prepared.atr.iloc[i])
        engine.atr[entry - 1] = atr
        trade = engine.trade(entry, d, max(parameters["StopATR"] * atr, parameters["MinDistance"]),
            {"reward_r": parameters["TargetR"], "max_hold_minutes": 10**9}, "broker_parity", len(m5)-1)
        records.append(trade)
        last = trade["exit_index"]
        daily[trade["exit_day"]] = daily.get(trade["exit_day"], 0) + trade["r_multiple"]
    columns = ["entry_ts", "exit_ts", "dir", "entry", "exit", "exit_reason", "atr", "distance", "r_multiple"]
    trades = pd.DataFrame(records, columns=columns)
    return trades, raw, prepared, m5


def diff_trades(native, expected):
    """Outer join: unmatched entries on either side count against the denominator."""
    left, right = native.copy(), expected.copy()
    for data in (left, right):
        for label in ("entry", "exit"):
            if f"{label}_utc" in data:
                stamps = pd.to_datetime(data[f"{label}_utc"], unit="s", utc=True)
            else:
                stamps = pd.to_datetime(data[f"{label}_ts"], utc=True)
            data[f"{label}_bar"] = stamps.dt.floor("5min")
        if data.duplicated(["entry_bar", "dir"]).any():
            raise ValueError("Duplicate entry keys: cannot use a many-to-many parity join")
    compared = left.merge(right, on=["entry_bar", "dir"], how="outer", suffixes=("_ea", "_python"), indicator=True)
    match = (compared._merge.eq("both") & compared.exit_bar_ea.eq(compared.exit_bar_python)
             & compared.exit_reason_ea.eq(compared.exit_reason_python))
    compared["match"] = match
    total = len(compared)
    ratio = float(match.mean()) if total else None
    status = "INSUFFICIENT_DATA" if not total else "PASS" if ratio >= .95 else "FAIL"
    return {"status": status, "native_trades": len(native), "python_trades": len(expected),
            "comparison_rows": total, "matching_trades": int(match.sum()), "match_ratio": ratio}, compared


def collect(output):
    if (output / "FROZEN.json").exists():
        raise PermissionError("Refusing to overwrite a frozen run; start a new attempt")
    terminal = Terminal()
    run = json.loads((output / "STARTED.json").read_text())
    run_id = run["run_id"]
    for kind in ("ticks.bin", "signals.csv", "trades.csv", "meta.csv"):
        source = terminal.common / f"H01_{run_id}_{kind}"
        if not source.exists():
            raise RuntimeError(f"Tester has not produced {kind}")
        shutil.copy2(source, output / kind)
    report = terminal.root / "reports/GoldnixH01" / f"{run_id}_report.htm"
    if report.exists():
        shutil.copy2(report, output / "tester_report.htm")
        for asset in report.parent.glob(f"{run_id}_report*.png"):
            shutil.copy2(asset, output / asset.name)
    journal_lines = []
    candidates = list((terminal.root / "Tester").glob("**/logs/20261112.log"))
    # Local agent storage can live alongside, rather than inside, the terminal.
    candidates += list(terminal.prefix.glob("drive_c/users/*/AppData/Roaming/MetaQuotes/Tester/**/logs/20261112.log"))
    for path in candidates:
        lines = path.read_text(encoding="utf-16", errors="replace").splitlines()
        starts = [i for i, line in enumerate(lines) if "H01Channel" in line
                  and ("testing" in line or "test Experts" in line) and "finished" not in line]
        chosen = lines[starts[-1]:] if starts else lines[-100:]
        clean = [re.sub(r"\b\d{9,12}\b", "[redacted_id_or_epoch]", line) for line in chosen]
        journal_lines.extend(clean)
    (output / "tester_journal.txt").write_text("\n".join(journal_lines)+"\n")


def analyse(output):
    if (output / "FROZEN.json").exists():
        raise PermissionError("Refusing to overwrite a frozen run; start a new attempt")
    decision = json.loads((output / "decision.json").read_text())
    meta = dict(pd.read_csv(output / "meta.csv", dtype=str).itertuples(index=False, name=None))
    if meta.get("completed") != "1" or meta.get("tester") != "1":
        raise RuntimeError("No completed Strategy Tester receipt")
    payload = output / "ticks.bin"
    if payload.stat().st_size % TICK_DTYPE.itemsize:
        raise ValueError("Truncated tick archive")
    ticks = np.fromfile(payload, dtype=TICK_DTYPE)
    if len(ticks) == 0 or len(ticks) != int(meta["ticks"]):
        raise ValueError("Missing or inconsistent tick count")
    if (np.diff(ticks["server_msc"]) < 0).any() or (ticks["ask"] < ticks["bid"]).any():
        raise ValueError("Invalid tick chronology or quotes")
    expected, raw, prepared, m5 = reference(ticks, decision)
    expected.to_csv(output / "python_trades.csv", index=False)
    raw.to_csv(output / "broker_h1.csv", index=False)
    m5.to_csv(output / "broker_m5.csv", index=False)
    native = pd.read_csv(output / "trades.csv")
    timestamp_audit = audit(native, decision["operational_inputs"])
    parity, compared = diff_trades(native, expected)
    compared.to_csv(output / "trade_comparison.csv", index=False)
    compared.loc[~compared.match].to_csv(output / "mismatches.csv", index=False)
    signals = pd.read_csv(output / "signals.csv")
    raw["signal_utc"] = raw.epoch_seconds
    checked = signals.merge(raw[["signal_utc", "signal", "atr", "bid_close", "ask_close"]],
                            on="signal_utc", how="left", suffixes=("_ea", "_python"), validate="one_to_one")
    checked["atr_error"] = abs(checked.atr_ea-checked.atr_python)
    checked["distance_error"] = abs(checked.distance-np.maximum(
        checked.atr_python*decision["inputs"]["StopATR"], decision["inputs"]["MinDistance"]))
    checked["spread_error"] = abs(checked.spread-(checked.ask_close-checked.bid_close))
    checked["match"] = (checked.direction.eq(checked.signal) & checked.atr_error.le(1e-8)
                        & checked.distance_error.le(1e-8) & checked.spread_error.le(1e-8))
    checked.to_csv(output / "signal_comparison.csv", index=False)
    journal = (output / "tester_journal.txt").read_text()
    quality = [line for line in journal.splitlines() if re.search("absent|discard|generat|mismatch|no history|no data|real ticks", line, re.I)]
    failures = []
    if meta.get("failed") != "0":
        failures.append("native_data_error")
    if int(meta.get("rejected_orders", "0")):
        failures.append("native_order_rejection")
    if int(meta.get("unreconciled_position", "0")):
        failures.append("unreconciled_native_position")
    if not len(checked) or not checked.match.all():
        failures.append("signal_comparison_failed_or_empty")
    if not (output / "tester_report.htm").exists():
        failures.append("native_tester_report_missing")
    if "callback_ticks" in meta and int(meta["callback_ticks"]) != len(ticks):
        failures.append("callback_and_archive_tick_counts_differ")
    if "first_callback_server_msc" in meta and int(meta["first_callback_server_msc"]) != ticks["server_msc"][0]:
        failures.append("callback_and_archive_start_differ")
    if "last_callback_server_msc" in meta and int(meta["last_callback_server_msc"]) != ticks["server_msc"][-1]:
        failures.append("callback_and_archive_end_differ")
    risk_skips = signals.loc[signals.reason.eq("risk_cap")]
    risks = (risk_skips.distance+risk_skips.spread)*decision["inputs"]["USDPerPriceUnit"]
    clock = json.loads((output / "CLOCK_CHECK.json").read_text()) if (output / "CLOCK_CHECK.json").exists() else None
    clock_pass = bool(clock and clock["passed"] and clock["selected_offset_seconds"] == decision["operational_inputs"]["ServerOffsetSeconds"])
    blockers = ["Step7 missing for H01"]
    if not clock_pass:
        blockers.append("Historical UTC offset not independently validated for this window")
    engineering_status = ("PASS" if parity["status"] == "PASS" and not failures and clock_pass
                          else "FAIL" if failures else parity["status"])
    result = {"candidate": decision["candidate_id"], "step8_status": "NOT_PASSED",
        "engineering_status": engineering_status,
        "engineering_parity": parity, "native_receipt": meta,
        "timestamp_audit": timestamp_audit, "clock_alignment_passed": clock_pass,
        "price_model": decision.get("data_model", "Real-tick mode; broker CopyTicks archive"),
        "signal_comparison": {"rows": len(checked), "matched": int(checked.match.sum()),
                              "max_atr_error": float(checked.atr_error.max()) if len(checked) else None},
        "native_skip_counts": signals.reason.value_counts().to_dict(),
        "risk_cap_rejections": {"buy": int(risk_skips.direction.eq(1).sum()),
                                "sell": int(risk_skips.direction.eq(-1).sum()),
                                "min_planned_usd": float(risks.min()) if len(risks) else None,
                                "max_planned_usd": float(risks.max()) if len(risks) else None,
                                "cap_usd": decision["inputs"]["ReferenceAccountUSD"]*decision["inputs"]["RiskShare"]},
        "broker_data": {"ticks": len(ticks), "h1_bars": len(raw), "m5_bars": len(m5),
                        "first_bar_utc": str(m5.timestamp_utc.min()), "last_bar_utc": str(m5.timestamp_utc.max()),
                        "sha256": hashlib.sha256(payload.read_bytes()).hexdigest()},
        "runtime_failures": failures, "tester_data_quality_lines": quality,
        "qualification_blockers": blockers,
        "step7_passed": False, "forward_approved": False,
        "completed_utc": datetime.now(UTC).isoformat()}
    (output / "RESULT.json").write_text(json.dumps(result, indent=2, allow_nan=False)+"\n")
    print(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    output = Path(json.loads((HERE / "LATEST.json").read_text())["output"])
    collect(output)
    analyse(output)
