"""Local deployment and read-only inspection for the persistent MT5 demo EA."""

import argparse
import csv
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import time

from goldnix_venue.demo_session import Terminal, write_json

HERE = Path(__file__).resolve().parent
DEPLOY = HERE / "deployment"


def status():
    path = Terminal().root / "MQL5/Files/GoldnixAutoM5Demo/status.csv"
    if not path.exists():
        return {"state": "not_started"}
    with path.open() as file:
        return {r["key"]: r["value"] for r in csv.DictReader(file)}


def truth(value):
    return str(value).lower() in ("true", "1")


def close_terminal(terminal):
    terminal.close()
    for _ in range(80):
        processes = subprocess.run(["ps", "-axo", "comm"], capture_output=True, text=True).stdout
        if not any(
            p.strip().lower().endswith(("/terminal64.exe", "\\terminal64.exe"))
            for p in processes.splitlines()
        ):
            return
        time.sleep(0.25)
    raise TimeoutError("MT5 did not finish closing")


def wait_ready(previous_folder=None, started=0):
    for _ in range(120):
        current = status()
        fresh = time.time() - int(current.get("captured_utc", "0")) < 15
        if (
            fresh
            and int(current.get("captured_utc", "0")) >= started
            and truth(current.get("data_ready"))
            and not current.get("state", "").startswith("Stopped")
            and (previous_folder is None or current.get("run_folder") != previous_folder)
        ):
            if truth(current.get("state_broken")) or truth(current.get("audit_halt")):
                raise ValueError("Native checkpoint/audit halt")
            return current
        time.sleep(1)
    raise TimeoutError("Native capture did not become ready")


def compile_all(install=True):
    terminal = Terminal()
    DEPLOY.mkdir(exist_ok=True)
    headers = (
        "AutoM1Policy.mqh",
        "ProfitPolicy.mqh",
        "ProfitJournal.mqh",
        "ProfitManager.mqh",
        "ProfitPolicyCases.mqh",
    )
    for header in headers:
        shutil.copy2(HERE / header, terminal.build / header)
    hashes = {}
    for name in ("AutoM1PolicyProbe", "GoldnixAutoM1", "ProfitBrokerProbe"):
        shutil.copy2(HERE / f"{name}.mq5", terminal.build / f"{name}.mq5")
        log = terminal.build / f"{name}_compile.log"
        log.unlink(missing_ok=True)
        subprocess.run(
            [
                str(terminal.wine),
                str(terminal.root / "metaeditor64.exe"),
                f"/compile:C:\\Goldnix\\{name}.mq5",
                f"/log:C:\\Goldnix\\{name}_compile.log",
            ],
            env=terminal.env,
            capture_output=True,
            timeout=60,
        )
        content = log.read_text(encoding="utf-16")
        (DEPLOY / log.name).write_text(content)
        if "0 errors, 0 warnings" not in content:
            raise RuntimeError(f"Native compile failed: inspect {DEPLOY / log.name}")
        target = (
            terminal.root / "MQL5" / ("Scripts" if name == "AutoM1PolicyProbe" else "Experts") / "Goldnix"
        )
        if install:
            target.mkdir(parents=True, exist_ok=True)
            for header in headers:
                shutil.copy2(HERE / header, target / header)
        for suffix in ("mq5", "ex5"):
            source = terminal.build / f"{name}.{suffix}"
            if install:
                shutil.copy2(source, target / source.name)
            shutil.copy2(source, DEPLOY / source.name)
            hashes[str((target / source.name).relative_to(terminal.root))] = hashlib.sha256(
                source.read_bytes()
            ).hexdigest()
    for header in headers:
        hashes["MQL5/Experts/Goldnix/" + header] = hashlib.sha256((HERE / header).read_bytes()).hexdigest()
    write_json(DEPLOY / ("COMPILED.json" if install else "STAGED.json"), hashes)
    return {"compiled": 3, "errors": 0, "warnings": 0, "installed": install}


def wait_file(path, start, timeout=110):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists() and path.stat().st_mtime >= start:
            return
        time.sleep(1)
    raise TimeoutError(f"Native output missing: {path.name}")


def verify_signals():
    import numpy as np
    import pandas as pd
    from goldnix_research.candidates import prepare_candidate

    s = status()
    if s.get("program") != "GoldnixAutoM1" or s.get("bar_seconds") != "60":
        raise ValueError("Current terminal status is not the M1 EA")
    folder = Terminal().root / "MQL5/Files" / s["run_folder"].replace("\\", "/")
    bars = pd.read_csv(folder / "m1.csv")
    signals = pd.read_csv(folder / "signals.csv")
    price_columns = [c for c in bars if c.startswith(("bid_", "ask_"))]
    if (bars.groupby("epoch_seconds")[price_columns].nunique() > 1).any().any():
        raise ValueError("Repeated bar changed across resynchronization")
    bars = bars.drop_duplicates("epoch_seconds").sort_values("epoch_seconds")
    if len(bars) < 100 or signals.empty:
        raise ValueError("Native warmup is not complete")
    reference = prepare_candidate(bars, {"family": "channel", "period": 20})
    compared = signals.merge(
        reference[["epoch_seconds", "signal", "atr", "bid_open", "ask_open", "bid_close", "ask_close"]],
        left_on="signal_utc",
        right_on="epoch_seconds",
        suffixes=("_native", "_python"),
        validate="many_to_one",
    )
    distance = np.maximum(2 * compared.atr_python, 0.5)
    spread = compared.ask_close - compared.bid_close
    execution_check = compared.context.eq("requested_execution_check")
    check_sizing_ok = (4 - spread).ge(0.5)
    distance = np.where(execution_check & check_sizing_ok, np.minimum(distance, 4 - spread), distance)
    candle_direction = np.sign(
        (compared.bid_close + compared.ask_close) / 2 - (compared.bid_open + compared.ask_open) / 2
    )
    expected_direction = np.where(execution_check, candle_direction, compared.signal)
    valid = (
        compared.direction.eq(expected_direction)
        & (compared.atr_native - compared.atr_python).abs().lt(1e-8)
        & (compared.distance - distance).abs().lt(1e-8)
        & (compared.spread - spread).abs().lt(1e-8)
        & (compared.nominal_usd - (distance + spread) * 0.01).abs().lt(1e-8)
        & compared.decision_utc.ge(compared.signal_utc + 60)
        & (~execution_check | compared.decision_utc.lt(compared.signal_utc + 70))
    )
    result = {
        "run_folder": str(folder),
        "signals": len(signals),
        "matched": int(valid.sum()),
        "execution_check_decisions": int(execution_check.sum()),
        "passed": len(compared) == len(signals) and bool(valid.all()),
    }
    compared.assign(match=valid).to_csv(DEPLOY / "signal_comparison.csv", index=False)
    write_json(DEPLOY / "SIGNAL_CHECK.json", result)
    if not result["passed"]:
        raise ValueError("Native signals differ from independent Python calculation")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("compile", "compile-staged", "status", "verify-signals"))
    command = parser.parse_args().command
    result = (
        compile_all(install=command == "compile")
        if command.startswith("compile")
        else verify_signals()
        if command == "verify-signals"
        else status()
    )
    print(json.dumps(result, indent=2), flush=True)


if __name__ == "__main__":
    main()
