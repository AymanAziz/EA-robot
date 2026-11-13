"""Daily local DEMO session controller: install, check, status, stop, disable."""

import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import shutil
import signal
import subprocess
import sys
import time
from datetime import UTC, datetime
from decimal import Decimal

from goldnix_step9_m5_demo.policy import flatten_deadline, make_run, reconcile
from goldnix_venue.demo_session import Terminal, rows, validate_account, write_json

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DEPLOY = HERE / "deployment"
LABEL = "local.goldnix.m05.daily-demo"
PLIST = Path.home() / "Library/LaunchAgents" / f"{LABEL}.plist"


def utc():
    return datetime.now(UTC).isoformat()


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compile_native():
    terminal = Terminal()
    DEPLOY.mkdir(exist_ok=True)
    source = HERE / "M05Session.mq5"
    shutil.copy2(source, terminal.build / source.name)
    log = terminal.build / "M05Session_compile.log"
    log.unlink(missing_ok=True)
    subprocess.run([str(terminal.wine), str(terminal.root / "metaeditor64.exe"),
        "/compile:C:\\Goldnix\\M05Session.mq5", "/log:C:\\Goldnix\\M05Session_compile.log"],
        env=terminal.env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60)
    content = log.read_text(encoding="utf-16")
    (DEPLOY / "compile.log").write_text(content)
    if "0 errors, 0 warnings" not in content:
        raise RuntimeError(f"Inspect {DEPLOY / 'compile.log'}")
    installed = {}
    for suffix in ("mq5", "ex5"):
        file = terminal.build / f"M05Session.{suffix}"
        shutil.copy2(file, terminal.root / "MQL5/Scripts/Goldnix" / file.name)
        shutil.copy2(file, DEPLOY / file.name)
        installed[file.name] = digest(file)
    return installed


def preset(terminal, run, mode, *, offset=0):
    filename = f"{run['run_id']}_mode{mode}.set"
    terminal.preset(filename, {"ExpectedLogin": terminal.expected_login, "RunId": run["run_id"],
        "MagicBase": run["magic_base"], "Mode": mode,
        # Native ScriptParameters parses datetime text as a leading integer in
        # this terminal build. Epoch seconds survive that parser exactly.
        "StartUTC": run["start_utc"], "EndUTC": run["end_utc"],
        "ExpectedOffsetSeconds": offset, "StopFile": f"goldnix_m05_{run['run_id']}.stop",
        "MaxTrades": run["max_trades"], "SessionLossLimitUSC": run["loss_limit_usc"]})
    path = terminal.build / f"{run['run_id']}_mode{mode}.ini"
    enabled = int(mode in (1, 2))
    path.write_text(f"[Experts]\nEnabled={enabled}\nAllowLiveTrading={enabled}\nAllowDllImport=0\nAccount=1\nProfile=1\n"
        f"\n[StartUp]\nScript=Goldnix\\M05Session\nScriptParameters={filename}\nSymbol=XAUUSD.c\nPeriod=M5\nShutdownTerminal=0\n")
    return path


def cleanup_presets(terminal, run):
    for path in (terminal.root / "MQL5/Presets").glob(f"{run['run_id']}_*.set"):
        path.unlink(missing_ok=True)


def native_receipt(terminal, run):
    values = rows(terminal.common / f"goldnix_m05_{run['run_id']}_receipt.csv")
    return {row["key"]: row["value"] for row in values}


def validate_timeframe(receipt):
    if receipt.get("signal_timeframe") != "M5" or str(receipt.get("bar_seconds")) != "300":
        raise ValueError("Native session must use completed M5 bars")


def copy_logs(terminal, run, output):
    for path in terminal.common.glob(f"goldnix_m05_{run['run_id']}_*.csv"):
        shutil.copy2(path, output / path.name.removeprefix(f"goldnix_m05_{run['run_id']}_"))


def check_signals(output):
    import numpy as np
    import pandas as pd
    from goldnix_research.candidates import prepare_candidate

    bars = pd.read_csv(output / "m5.csv")
    signals = pd.read_csv(output / "signals.csv")
    if len(bars) < 100 or signals.empty:
        raise ValueError("No warmed native signal to check")
    calculated = prepare_candidate(bars, {"family": "channel", "period": 20})
    compared = signals.merge(calculated[["epoch_seconds", "signal", "atr", "bid_close", "ask_close"]],
        left_on="signal_utc", right_on="epoch_seconds", suffixes=("_native", "_python"), validate="many_to_one")
    if len(compared) != len(signals):
        raise ValueError("Native signals have missing historical inputs")
    errors = (compared.atr_native-compared.atr_python).abs()
    distances = np.maximum(compared.atr_python*2, .5)
    spread = compared.ask_close-compared.bid_close
    matched = (compared.direction.eq(compared.signal) & errors.lt(1e-8)
        & (compared.distance-distances).abs().lt(1e-8) & (compared.spread-spread).abs().lt(1e-8)
        & (compared.nominal_usd-(distances+spread)*.01).abs().lt(1e-8)
        & compared.decision_utc.ge(compared.signal_utc+300))
    compared["match"] = matched
    compared.to_csv(output / "signal_comparison.csv", index=False)
    result = {"signals": len(compared), "matched": int(matched.sum()), "max_atr_error": float(errors.max()),
              "passed": bool(matched.all())}
    write_json(output / "SIGNAL_CHECK.json", result)
    if not result["passed"]:
        raise ValueError("Native signal calculations differ from Python")
    return result


def check():
    lock = (Terminal().build / "demo_session.lock").open("a")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    installed = compile_native()
    run = make_run(datetime.now(UTC), check=True)
    if not run["inside"]:
        raise ValueError("Native preflight is bounded to the requested midnight–06:30 window")
    output = HERE / "out" / run["run_id"]
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "SESSION.json", run)
    terminal = Terminal()
    terminal.expected_login = terminal.login()
    terminal.check_charts()
    try:
        snapshot, history = terminal.verify(run, output, "before")
        validate_account(snapshot, flat=True, disabled=True)
        if history:
            raise ValueError("Today's strategy magic already has history")
        terminal.restart(preset(terminal, run, 0), output, disable=True)
        for _ in range(240):
            receipt = native_receipt(terminal, run)
            if receipt.get("state") in ("ready", "aborted"):
                copy_logs(terminal, run, output)
                if receipt["state"] != "ready":
                    raise RuntimeError(f"Native preflight aborted: inspect {output}")
                validate_timeframe(receipt)
                if any(receipt.get(k) != "0" for k in ("positions", "orders", "terminal_trade_allowed", "script_trade_allowed", "entry_attempts")):
                    raise RuntimeError("Read-only preflight state invalid")
                signal_check = check_signals(output)
                result = {"passed": True, "output": str(output), "installed_sha256": installed,
                    "signal_timeframe": "M5", "bar_seconds": 300,
                    "server_offset_seconds": int(receipt["server_offset_seconds"]),
                    "market_end_utc": int(receipt["current_market_end_utc"]), "signal_check": signal_check,
                    "account_identity_sha256": hashlib.sha256(terminal.expected_login.encode()).hexdigest(),
                    "checked_utc": utc()}
                write_json(DEPLOY / "PREFLIGHT.json", result)
                print(json.dumps(result, indent=2), flush=True)
                return result
            time.sleep(1)
        raise TimeoutError("Native history preflight did not finish")
    finally:
        cleanup_presets(terminal, run)
        lock.close()


def verify_deployment(terminal):
    manifest = json.loads((DEPLOY / "MANIFEST.json").read_text())
    for name, expected in manifest["source_sha256"].items():
        if digest(ROOT / name) != expected:
            raise ValueError(f"Deployed source changed: {name}")
    for name, expected in manifest["installed_sha256"].items():
        if digest(terminal.root / "MQL5/Scripts/Goldnix" / name) != expected:
            raise ValueError("Installed native session binary/source changed")
    return manifest


def report(terminal, run, output, initial_balance, reason):
    snapshot, history = terminal.verify(run, output, "final")
    validate_account(snapshot, flat=True, disabled=True)
    trades = reconcile(history, run["magic_base"], run["max_trades"])
    pnl = sum((Decimal(str(t["pnl_usc"])) for t in trades), Decimal(0))
    if pnl != Decimal(snapshot["net_pnl_usc"]):
        raise ValueError("Broker history P&L and receipt differ")
    if initial_balance is not None and Decimal(initial_balance)+pnl != Decimal(snapshot["balance_usc"]):
        raise ValueError("Account balance changed outside the session")
    copy_logs(terminal, run, output)
    archive = terminal.common / f"goldnix_m05_{run['run_id']}_session_ticks.bin"
    if archive.exists():
        shutil.copy2(archive, output / "session_ticks.bin")
    comparison = check_signals(output) if (output / "signals.csv").exists() else None
    events = rows(output / "events.csv")
    actual_starts = [int(row["utc_epoch"]) for row in events if row["event"] == "SESSION_START"]
    actual_ends = [int(row["utc_epoch"]) for row in events if row["event"] == "END"]
    receipt = {"session_date": run["date"], "variant": run["variant"], "state": "verified_complete", "stop_reason": reason,
        "signal_timeframe": "M5", "bar_seconds": 300,
        "trades": trades, "completed_trades": len(trades), "wins": sum(t["pnl_usc"]>0 for t in trades),
        "losses": sum(t["pnl_usc"]<0 for t in trades), "net_pnl_usc": float(pnl), "net_pnl_usd": float(pnl/100),
        "balance_usc": float(snapshot["balance_usc"]), "positions": 0, "orders": 0, "automation_enabled": False,
        "signal_comparison": comparison, "verified_utc": utc(), "step7_passed": False,
        "formal_step9_qualified": False, "user_authorized_experimental_demo": True,
        "quote_archive_bytes": archive.stat().st_size if archive.exists() else 0,
        "quote_archive_complete": (native_receipt(terminal, run).get("mode") == "1"
            and native_receipt(terminal, run).get("state") == "complete"
            and native_receipt(terminal, run).get("quote_archive_complete") == "1"),
        "actual_start_utc": actual_starts[0] if actual_starts else None,
        "actual_end_utc": actual_ends[-1] if actual_ends else None,
        "scheduled_end_utc": run["end_utc"]}
    write_json(output / "RECEIPT.json", receipt)
    write_json(output / "STATUS.json", receipt)
    (output / "SUMMARY.md").write_text(f"# M5 channel demo — {run['date']}\n\n"
        f"{len(trades)} closed trades; net **{float(pnl):+.2f} USC ({float(pnl/100):+.4f} USD)**. "
        f"Balance {receipt['balance_usc']:.2f} USC. Account flat; automation disabled and verified.\n\n"
        f"Stop reason: {reason}. Session: midnight–06:30 Asia/Kuala_Lumpur, with earlier flattening before broker breaks.\n\n"
        "This M5 channel demo retains the $0.05 planned-risk filter and adds a session cutoff, "
        "broker-session buffer, actual-risk check and 10 USC loss guard. It is separate from the frozen H01 "
        "research; formal Step7 qualification remains missing.\n\n"
        "[Receipt](RECEIPT.json) · [Native signals](signals.csv) · [Signal comparison](SIGNAL_CHECK.json) "
        "· [Broker history](final_history.csv)\n")
    return receipt


def worker():
    terminal = Terminal()
    lock = (terminal.build / "demo_session.lock").open("a")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return
    if not json.loads((DEPLOY / "SCHEDULE.json").read_text()).get("enabled"):
        return
    # An unresolved earlier run blocks new entries, including after reboot.
    blocked = HERE / "BLOCKED.json"
    if blocked.exists():
        return
    pending = HERE / "PENDING.json"
    if pending.exists():
        output = Path(json.loads(pending.read_text())["output"])
        run = json.loads((output / "SESSION.json").read_text())
    else:
        run = make_run(datetime.now(UTC))
        output = HERE / "out" / run["date"]
        if (output / "RECEIPT.json").exists() or not run["inside"]:
            return
    output.mkdir(parents=True, exist_ok=True)
    recovering = (output / "STARTED.json").exists()
    if recovering:
        run = json.loads((output / "SESSION.json").read_text())
    else:
        write_json(output / "SESSION.json", run)
        with (output / "STARTED.json").open("x") as file:
            json.dump({"started_utc": utc(), "new_entries_attempted_once": True}, file)
    write_json(pending, {"output": str(output), "run_id": run["run_id"]})
    write_json(HERE / "LATEST_SESSION.json", {"output": str(output), "run_id": run["run_id"]})
    stop = terminal.common / f"goldnix_m05_{run['run_id']}.stop"
    keep_awake = subprocess.Popen(["/usr/bin/caffeinate", "-i", "-s", "-w", str(os.getpid())],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    def request_stop(signum, frame):
        stop.write_text(f"Controller received signal {signum}")
    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    initial_balance = None
    reason = "startup"
    launched = False
    identity_checked = False
    try:
        manifest = verify_deployment(terminal)
        if not (output / "source").exists():
            (output / "source").mkdir()
            for path in HERE.iterdir():
                if path.suffix in (".py", ".mq5"):
                    shutil.copy2(path, output / "source" / path.name)
            shutil.copy2(DEPLOY / "M05Session.ex5", output / "source/M05Session.ex5")
            write_json(output / "DEPLOYMENT.json", manifest)
        terminal.expected_login = terminal.login()
        if hashlib.sha256(terminal.expected_login.encode()).hexdigest() != manifest["account_identity_sha256"]:
            raise ValueError("Saved account identity changed")
        identity_checked = True
        terminal.check_charts()
        write_json(output / "STATUS.json", {"state": "preflight", "updated_utc": utc(), "end_local": run["end_local"]})
        snapshot, history = terminal.verify(run, output, "initial")
        validate_account(snapshot, disabled=True)
        initial_balance = snapshot["balance_usc"] if not recovering else None
        if not recovering and (history or snapshot["positions"]!="0" or snapshot["orders"]!="0"):
            raise ValueError("New session requires a flat account without prior session trades")
        lid = subprocess.run(["/usr/sbin/ioreg", "-r", "-k", "AppleClamshellState", "-d", "4"], capture_output=True, text=True).stdout
        if re.search(r'"AppleClamshellState"\s*=\s*Yes', lid):
            raise ValueError("Mac lid is closed")
        mode = 2 if recovering else 1
        launch_utc = int(time.time())
        terminal.restart(preset(terminal, run, mode, offset=0), output)
        launched = True
        last_loop = time.time()
        last_event = last_loop
        planned_flatten = flatten_deadline(run)
        while True:
            now = time.time()
            if now-last_loop>30:
                stop.write_text("Host paused or watchdog delayed")
            last_loop=now
            events = rows(terminal.common / f"goldnix_m05_{run['run_id']}_events.csv")
            if events:
                last_event = max(last_event, int(events[-1]["utc_epoch"]))
            native = native_receipt(terminal, run)
            if native.get("mode") != str(mode) or int(native.get("captured_utc", "0")) < launch_utc:
                native = {}
            if native:
                validate_timeframe(native)
            if int(native.get("current_market_end_utc", "0")) > 0:
                planned_flatten = flatten_deadline(run, int(native["current_market_end_utc"]))
            state = native.get("state", "warming_up")
            if native.get("identity_matches") == "0":
                raise ValueError("Native account identity changed")
            status = {"state": state, "updated_utc": utc(), "controller_pid": os.getpid(), "job": LABEL,
                "end_local": run["end_local"], "flatten_utc": planned_flatten,
                "native": native, "new_entries_enabled": mode==1 and state=="running"}
            write_json(output / "STATUS.json", status)
            copy_logs(terminal, run, output)
            if state in ("complete", "recovered_flat", "aborted", "needs_reconciliation"):
                reason = native.get("halt_reason") or state
                break
            if now>=run["end_utc"]:
                if not stop.exists():
                    stop.write_text("Daily 06:30 cutoff")
            if now-last_event>180 or (stop.exists() and now-stop.stat().st_mtime>90):
                reason="native_heartbeat_stale_or_stop_unconfirmed"
                stop.write_text(reason)
                break
            time.sleep(2)
    except Exception as exc:
        reason=f"controller_error: {exc}"
        write_json(output / "ERROR.json", {"error": str(exc), "utc": utc()})
    finally:
        stop.write_text(reason)
        write_json(output / "STATUS.json", {"state": "reconciling", "reason": reason, "updated_utc": utc()})
        try:
            if not identity_checked:
                raise ValueError("Account identity was not verified; no terminal mutation during cleanup")
            if launched:
                snapshot, history = terminal.verify(run, output, "before_recovery")
                validate_account(snapshot, disabled=True)
                if snapshot["positions"]!="0" or snapshot["orders"]!="0":
                    recovery_utc = int(time.time())
                    terminal.restart(preset(terminal, run, 2), output)
                    for _ in range(330):
                        recovery = native_receipt(terminal, run)
                        if (recovery.get("mode") == "2" and int(recovery.get("captured_utc", "0")) >= recovery_utc
                                and recovery.get("state") in ("recovered_flat", "needs_reconciliation")):
                            break
                        time.sleep(2)
            result = report(terminal, run, output, initial_balance, reason)
            write_json(HERE / "LAST_COMPLETE.json", {"output": str(output), "session_date": run["date"], "completed_utc": result["verified_utc"]})
            pending.unlink(missing_ok=True)
        except Exception as exc:
            failure={"state": "needs_reconciliation", "output": str(output), "error": str(exc), "utc": utc(), "new_entries_blocked": True}
            write_json(output / "STATUS.json", failure)
            write_json(blocked, failure)
        cleanup_presets(terminal, run)
        keep_awake.terminate()


def install():
    preflight = json.loads((DEPLOY / "PREFLIGHT.json").read_text())
    if not preflight["passed"]:
        raise ValueError("Native preflight must pass")
    validate_timeframe(preflight)
    if digest(HERE / "M05Session.mq5") != preflight["installed_sha256"]["M05Session.mq5"]:
        raise ValueError("Native source changed since the read-only check")
    # Calendar scheduling follows the Mac timezone; runtime also enforces Malaysia boundaries.
    if time.localtime().tm_gmtoff != 8*3600:
        raise ValueError("Mac timezone is not UTC+8; calendar schedule needs adjustment")
    manifest = {"created_utc": utc(), "installed_sha256": preflight["installed_sha256"],
        "account_identity_sha256": preflight["account_identity_sha256"],
        "source_sha256": {p.relative_to(ROOT).as_posix(): digest(p) for p in HERE.iterdir() if p.suffix in (".py", ".mq5")}}
    write_json(DEPLOY / "MANIFEST.json", manifest)
    write_json(DEPLOY / "SCHEDULE.json", {"enabled": True, "timezone": "Asia/Kuala_Lumpur", "start": "00:00", "stop": "06:30", "days": "every day",
        "signal_timeframe": "M5", "bar_seconds": 300, "variant": "M05_CHANNEL_SESSION_DEMO",
        "user_authorized": True, "user_authorized_experimental_demo": True, "formal_step9_qualified": False,
        "runtime_requires": "Mac awake, logged in, MT5 connected; native server SL/TP remains on owned positions", "created_utc": utc()})
    job = {"Label": LABEL, "ProgramArguments": [sys.executable, "-m", "goldnix_step9_m5_demo.runner", "_worker"],
        "WorkingDirectory": str(ROOT), "EnvironmentVariables": {"PYTHONPATH": f"{ROOT}:{ROOT / 'goldnix'}"},
        "RunAtLoad": True, "StartCalendarInterval": {"Hour": 0, "Minute": 0},
        "KeepAlive": {"SuccessfulExit": False}, "ThrottleInterval": 60, "ExitTimeOut": 180,
        "ProcessType": "Background", "StandardOutPath": str(DEPLOY / "controller.stdout.log"),
        "StandardErrorPath": str(DEPLOY / "controller.stderr.log")}
    PLIST.parent.mkdir(parents=True, exist_ok=True)
    if PLIST.exists():
        raise FileExistsError("Schedule already installed; inspect before replacing")
    PLIST.write_bytes(plistlib.dumps(job))
    subprocess.run(["launchctl", "bootstrap", f"gui/{os.getuid()}", str(PLIST)], check=True, capture_output=True)
    print(json.dumps({"installed": True, "job": LABEL, "window": "00:00–06:30 Asia/Kuala_Lumpur", "starts_now_if_inside_window": True}))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("check", "install", "status", "stop", "disable", "_worker"))
    command=parser.parse_args().command
    if command=="check":
        check()
    elif command=="install":
        install()
    elif command=="_worker":
        worker()
    elif command=="status":
        latest=HERE / "LATEST_SESSION.json"
        if latest.exists():
            output=Path(json.loads(latest.read_text())["output"])
            print((output / "STATUS.json").read_text())
        else:
            print(json.dumps({"state": "not_started"}))
    else:
        if command=="disable":
            schedule=json.loads((DEPLOY / "SCHEDULE.json").read_text())
            schedule["enabled"]=False
            write_json(DEPLOY / "SCHEDULE.json", schedule)
        latest=HERE / "LATEST_SESSION.json"
        if latest.exists():
            run=json.loads(latest.read_text())
            (Terminal().common / f"goldnix_m05_{run['run_id']}.stop").write_text("User requested stop")
        print("Stop requested; close/reconcile owned positions. " + ("Future sessions disabled." if command=="disable" else "Daily schedule remains enabled."))


if __name__=="__main__":
    main()
