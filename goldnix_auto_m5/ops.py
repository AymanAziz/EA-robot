"""Local deployment and read-only inspection for the persistent MT5 demo EA."""
import argparse
import csv
import fcntl
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import time
from datetime import UTC, datetime

from goldnix_venue.demo_session import Terminal, validate_account, write_json
from goldnix_step9_m5_demo.policy import make_run

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
        if not any(p.strip().lower().endswith(("/terminal64.exe", "\\terminal64.exe")) for p in processes.splitlines()):
            return
        time.sleep(.25)
    raise TimeoutError("MT5 did not finish closing")


def wait_ready(previous_folder=None, started=0):
    for _ in range(120):
        current = status()
        fresh = time.time()-int(current.get("captured_utc", "0")) < 15
        if (fresh and int(current.get("captured_utc", "0")) >= started
                and truth(current.get("data_ready")) and not current.get("state", "").startswith("Stopped")
                and (previous_folder is None or current.get("run_folder") != previous_folder)):
            if truth(current.get("state_broken")) or truth(current.get("audit_halt")):
                raise ValueError("Native checkpoint/audit halt")
            return current
        time.sleep(1)
    raise TimeoutError("Native capture did not become ready")


def compile_all():
    terminal = Terminal()
    DEPLOY.mkdir(exist_ok=True)
    shutil.copy2(HERE / "AutoPolicy.mqh", terminal.build / "AutoPolicy.mqh")
    hashes = {}
    for name in ("AutoPolicyProbe", "PersistM5Chart", "GoldnixAutoM5"):
        shutil.copy2(HERE / f"{name}.mq5", terminal.build / f"{name}.mq5")
        log = terminal.build / f"{name}_compile.log"
        log.unlink(missing_ok=True)
        subprocess.run([str(terminal.wine), str(terminal.root / "metaeditor64.exe"),
            f"/compile:C:\\Goldnix\\{name}.mq5", f"/log:C:\\Goldnix\\{name}_compile.log"],
            env=terminal.env, capture_output=True, timeout=60)
        content = log.read_text(encoding="utf-16")
        (DEPLOY / log.name).write_text(content)
        if "0 errors, 0 warnings" not in content:
            raise RuntimeError(f"Native compile failed: inspect {DEPLOY / log.name}")
        target = terminal.root / "MQL5" / ("Experts" if name == "GoldnixAutoM5" else "Scripts") / "Goldnix"
        target.mkdir(parents=True, exist_ok=True)
        shutil.copy2(HERE / "AutoPolicy.mqh", target / "AutoPolicy.mqh")
        for suffix in ("mq5", "ex5"):
            source = terminal.build / f"{name}.{suffix}"
            shutil.copy2(source, target / source.name)
            shutil.copy2(source, DEPLOY / source.name)
            hashes[str((target / source.name).relative_to(terminal.root))] = hashlib.sha256(source.read_bytes()).hexdigest()
    hashes["MQL5/Experts/Goldnix/AutoPolicy.mqh"] = hashlib.sha256((HERE / "AutoPolicy.mqh").read_bytes()).hexdigest()
    write_json(DEPLOY / "COMPILED.json", hashes)
    return {"compiled": 3, "errors": 0, "warnings": 0}


def wait_file(path, start, timeout=110):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists() and path.stat().st_mtime >= start:
            return
        time.sleep(1)
    raise TimeoutError(f"Native output missing: {path.name}")


def bootstrap():
    terminal = Terminal()
    lock = (terminal.build / "demo_session.lock").open("a")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    terminal.expected_login = terminal.login()
    terminal.check_charts()
    output = DEPLOY / ("bootstrap_" + datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ"))
    output.mkdir(parents=True, exist_ok=False)
    run = make_run(datetime.now(UTC), check=True)
    snapshot, history = terminal.verify(run, output, "before")
    validate_account(snapshot, flat=True, disabled=True)
    if history:
        raise ValueError("Unexpected earlier session history; review the handoff")
    print(json.dumps({"preflight_flat": True, "balance_usc": snapshot["balance_usc"]}), flush=True)
    for name, receipt in (("AutoPolicyProbe", "goldnix_auto_policy_probe.csv"), ("PersistM5Chart", "goldnix_persistent_chart.csv")):
        path = terminal.build / f"{name}_readonly.ini"
        path.write_text(f"[Experts]\nEnabled=0\nAllowLiveTrading=0\nAllowDllImport=0\n\n[StartUp]\nScript=Goldnix\\{name}\nSymbol=XAUUSD.c\nPeriod=M5\nShutdownTerminal=0\n")
        start = time.time()
        terminal.restart(path, output, disable=True)
        wait_file(terminal.common / receipt, start)
        shutil.copy2(terminal.common / receipt, output / receipt)
        with (output / receipt).open() as file:
            result = list(csv.DictReader(file))
        if name == "AutoPolicyProbe" and (len(result) != 1 or int(result[0]["failed"]) != 0):
            raise ValueError("Native behavior tests failed")
        print(json.dumps({name: result}), flush=True)
    terminal.close()
    profile = terminal.root / "MQL5/Profiles/Charts/Default"
    shutil.copytree(profile, output / "profile_before_ea")
    charts = sorted(profile.glob("*.chr"))
    if not charts:
        raise ValueError("Persistent chart was not saved")
    chart_text = charts[0].read_text(encoding="utf-16")
    if "symbol=XAUUSD.c" not in chart_text or "period_size=5" not in chart_text or "<expert>" in chart_text:
        raise ValueError("First saved chart is not an unattached XAUUSD.c M5 chart")
    write_json(DEPLOY / "BOOTSTRAP.json", {"output": str(output), "profile": str(profile),
        "native_behavior_tests": result if name == "AutoPolicyProbe" else list(csv.DictReader((output / "goldnix_auto_policy_probe.csv").open())),
        "account_identity_sha256": hashlib.sha256(terminal.expected_login.encode()).hexdigest(),
        "verified_utc": datetime.now(UTC).isoformat()})
    for p in (terminal.root / "MQL5/Presets").glob(f"{run['run_id']}_*.set"):
        p.unlink()
    print(json.dumps({"persistent_chart_prepared": True, "output": str(output)}), flush=True)


def attach(trading=False):
    terminal = Terminal()
    lock = (terminal.build / "demo_session.lock").open("a")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    bootstrap_record = json.loads((DEPLOY / "BOOTSTRAP.json").read_text())
    terminal.expected_login = terminal.login()
    if hashlib.sha256(terminal.expected_login.encode()).hexdigest() != bootstrap_record["account_identity_sha256"]:
        raise ValueError("Account changed since preparation")
    compiled = json.loads((DEPLOY / "COMPILED.json").read_text())
    for name, expected in compiled.items():
        if hashlib.sha256((terminal.root / name).read_bytes()).hexdigest() != expected:
            raise ValueError("Installed native artifacts changed")
    if trading and not json.loads((DEPLOY / "NORMAL_REOPEN_READONLY.json").read_text())["normal_app_reopen_passed"]:
        raise ValueError("Capture and persistence must pass before enabling demo entries")
    name = "GoldnixAutoM5_private.set"
    terminal.preset(name, {"ExpectedLogin": terminal.expected_login, "EnableDemoTrading": str(trading).lower()})
    config = terminal.build / "GoldnixAutoM5_attach.ini"
    # Symbol is deliberately omitted: attach to the saved profile's first chart.
    config.write_text(f"[Experts]\nEnabled=1\nAllowLiveTrading=1\nAllowDllImport=0\nAccount=1\nProfile=1\n\n[StartUp]\nExpert=Goldnix\\GoldnixAutoM5\nExpertParameters={name}\n")
    close_terminal(terminal)
    terminal.restart(config, DEPLOY)
    print(json.dumps({"attaching": True, "demo_trading": trading, "no_fixed_operating_hours": True}), flush=True)


def verify_signals():
    import numpy as np
    import pandas as pd
    from goldnix_research.candidates import prepare_candidate

    s = status()
    folder = Terminal().root / "MQL5/Files" / s["run_folder"].replace("\\", "/")
    bars = pd.read_csv(folder / "m5.csv")
    signals = pd.read_csv(folder / "signals.csv")
    price_columns = [c for c in bars if c.startswith(("bid_", "ask_"))]
    if (bars.groupby("epoch_seconds")[price_columns].nunique() > 1).any().any():
        raise ValueError("Repeated bar changed across resynchronization")
    bars = bars.drop_duplicates("epoch_seconds").sort_values("epoch_seconds")
    if len(bars) < 100 or signals.empty:
        raise ValueError("Native warmup is not complete")
    reference = prepare_candidate(bars, {"family": "channel", "period": 20})
    compared = signals.merge(reference[["epoch_seconds", "signal", "atr", "bid_close", "ask_close"]],
        left_on="signal_utc", right_on="epoch_seconds", suffixes=("_native", "_python"), validate="many_to_one")
    distance = np.maximum(2 * compared.atr_python, .5)
    spread = compared.ask_close - compared.bid_close
    valid = (compared.direction.eq(compared.signal) & (compared.atr_native-compared.atr_python).abs().lt(1e-8)
        & (compared.distance-distance).abs().lt(1e-8) & (compared.spread-spread).abs().lt(1e-8)
        & (compared.nominal_usd-(distance+spread)*.01).abs().lt(1e-8)
        & compared.decision_utc.ge(compared.signal_utc+300))
    result = {"run_folder": str(folder), "signals": len(signals), "matched": int(valid.sum()),
        "passed": len(compared) == len(signals) and bool(valid.all())}
    compared.assign(match=valid).to_csv(DEPLOY / "signal_comparison.csv", index=False)
    write_json(DEPLOY / "SIGNAL_CHECK.json", result)
    if not result["passed"]:
        raise ValueError("Native signals differ from independent Python calculation")
    return result


def verify_reopen_readonly():
    import numpy as np

    before = wait_ready()
    if truth(before["demo_trading_configured"]) or int(before["positions"]) or int(before["orders"]):
        raise ValueError("Reopen validation requires capture-only mode and a flat account")
    initial_check = verify_signals()
    terminal = Terminal()
    close_terminal(terminal)
    stopped = status()
    if not stopped["state"].startswith("Stopped"):
        raise ValueError("EA shutdown was not recorded")
    folder = terminal.root / "MQL5/Files" / stopped["run_folder"].replace("\\", "/")
    path = folder / "ticks.bin"
    if path.stat().st_size % 24:
        raise ValueError("Truncated captured quote record")
    quotes = np.fromfile(path, dtype=[("msc", "<i8"), ("bid", "<f8"), ("ask", "<f8")])
    if (len(quotes) != int(stopped["captured_ticks"]) or len(quotes) == 0
            or not (np.diff(quotes["msc"]) >= 0).all() or not (quotes["ask"] >= quotes["bid"]).all()
            or not (quotes["bid"] > 0).all()):
        raise ValueError("Captured quote stream failed integrity checks")
    charts = []
    for p in sorted((terminal.root / "MQL5/Profiles/Charts/Default").glob("*.chr")):
        text = p.read_text(encoding="utf-16")
        charts.append({"file": p.name, "saved_ea": "GoldnixAutoM5" in text,
            "m5": "period_size=5" in text, "symbol": "symbol=XAUUSD.c" in text})
    if sum(c["saved_ea"] for c in charts) != 1:
        raise ValueError("Expected exactly one persistent EA chart")
    start = int(time.time())
    subprocess.run(["open", "-a", str(Path.home() / "Applications/MetaTrader 5.app")], check=True)
    after = wait_ready(before["run_folder"], start)
    if (not truth(after["identity_matches"]) or not truth(after["connected"]) or not truth(after["exclusive_lock_verified"])
            or truth(after["demo_trading_configured"]) or truth(after["trade_permission"])
            or after["daily_attempts"] != before["daily_attempts"] or after["daily_r"] != before["daily_r"]
            or int(after["last_signal_utc"]) < int(before["last_signal_utc"])
            or int(after["state_sequence"]) <= int(before["state_sequence"])):
        raise ValueError("Normal reopen did not preserve the capture/risk state")
    result = {"verified_utc": datetime.now(UTC).isoformat(), "normal_app_reopen_passed": True,
        "startup_config_used": False, "saved_profile": charts, "before": before, "after": after,
        "captured_quote_records_verified": len(quotes), "initial_signal_check": initial_check,
        "signal_check": verify_signals(), "orders_sent_during_check": 0}
    write_json(DEPLOY / "NORMAL_REOPEN_READONLY.json", result)
    return {"normal_app_reopen_passed": True, "capture_ready": True, "counter_preserved": True,
        "captured_quote_records_verified": len(quotes), "signal_check": result["signal_check"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("compile", "bootstrap", "attach-readonly", "attach-demo", "status", "verify-signals", "verify-reopen-readonly"))
    command = parser.parse_args().command
    if command == "compile":
        result = compile_all()
    elif command == "bootstrap":
        result = bootstrap()
    elif command.startswith("attach-"):
        result = attach(command == "attach-demo")
    elif command == "verify-signals":
        result = verify_signals()
    elif command == "verify-reopen-readonly":
        result = verify_reopen_readonly()
    else:
        result = status()
    if result is not None:
        print(json.dumps(result, indent=2), flush=True)


if __name__ == "__main__":
    main()
