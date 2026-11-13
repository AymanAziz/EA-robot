"""Bounded local MT5 demo sessions. No AI/API dependency; never a live account.

python -m goldnix_venue.demo_session prepare
python -m goldnix_venue.demo_session start PATH
python -m goldnix_venue.demo_session status PATH
python -m goldnix_venue.demo_session stop PATH
"""
from __future__ import annotations

import argparse
import csv
import fcntl
import hashlib
import io
import json
import math
import os
from pathlib import Path
import plistlib
import re
import shutil
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from decimal import Decimal

SOURCE = Path(__file__).resolve().parent


def write_json(path, value):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n")
    temporary.replace(path)


def rows(path):
    path = Path(path)
    if not path.exists():
        return []
    # Ignore a final incomplete line while MT5 is appending/flushing.
    text = path.read_text(errors="replace")
    text = text[:text.rfind("\n") + 1]
    return list(csv.DictReader(io.StringIO(text)))


def fields(row):
    return dict(item.split("=", 1) for item in row.get("details", "").split(";") if "=" in item)


def utc(epoch=None):
    return datetime.fromtimestamp(time.time() if epoch is None else float(epoch), timezone.utc).isoformat()


def validate_account(snapshot, *, flat=False, disabled=False):
    expected = {"server": "JustMarkets-Demo6", "currency": "USC", "account_trade_mode": "0",
                "connected": "1", "history_selected": "1", "identity_matches": "1"}
    if flat:
        expected.update(positions="0", orders="0")
    if disabled:
        expected.update(terminal_trade_allowed="0", mql_trade_allowed="0")
    for key, value in expected.items():
        if str(snapshot.get(key)) != value:
            raise ValueError(f"Account check failed: {key}={snapshot.get(key)!r}, expected {value}")


def reconcile_history(history, magic_base, max_trades):
    """Use entry magic to identify positions; include exits regardless of magic."""
    unique = {}
    for row in history:
        if row["deal"] in unique and unique[row["deal"]] != row:
            raise ValueError("Conflicting duplicate deal")
        unique[row["deal"]] = row
    entries = [row for row in unique.values() if row["entry"] == "0"
               and magic_base < int(row["magic"]) <= magic_base + max_trades
               and row["symbol"] == "XAUUSD.c"]
    positions = {row["position"] for row in entries}
    result = []
    for position in positions:
        deals = [row for row in unique.values() if row["position"] == position]
        ins = [row for row in deals if row["entry"] == "0"]
        outs = [row for row in deals if row["entry"] in ("1", "3")]
        if len(ins) != 1 or len(outs) != 1:
            raise ValueError(f"Position {position} is not one fully closed round trip")
        entry, exit_ = ins[0], outs[0]
        if any(row["symbol"] != "XAUUSD.c" or Decimal(row["volume"]) != Decimal(".01") for row in deals):
            raise ValueError("Unexpected symbol or volume in history")
        pnl = sum((sum((Decimal(row[key]) for key in ("profit", "commission", "swap", "fee")), Decimal(0))
                   for row in deals), Decimal(0))
        if not pnl.is_finite():
            raise ValueError("Nonfinite P&L")
        held = int(exit_["time_server_epoch"]) - int(entry["time_server_epoch"])
        if held < 0:
            raise ValueError("Exit precedes entry")
        result.append({"index": int(entry["magic"]) - magic_base, "position": int(position),
                       "entry_deal": int(entry["deal"]), "exit_deal": int(exit_["deal"]),
                       "entry_price": float(entry["price"]), "exit_price": float(exit_["price"]),
                       "held_seconds": held, "pnl_usc": float(pnl), "exit_reason": exit_["reason"]})
    if len({trade["index"] for trade in result}) != len(result):
        raise ValueError("Repeated entry for the same trade index")
    return sorted(result, key=lambda row: row["index"])


class Terminal:
    def __init__(self):
        self.prefix = Path.home() / "Library/Application Support/net.metaquotes.wine.metatrader5"
        self.root = self.prefix / "drive_c/Program Files/MetaTrader 5"
        self.build = self.prefix / "drive_c/Goldnix"
        self.common = self.prefix / "drive_c/users" / Path.home().name / "AppData/Roaming/MetaQuotes/Terminal/Common/Files"
        self.wine = Path.home() / "Applications/MetaTrader 5.app/Contents/SharedSupport/wine/bin/wine"
        self.env = {**os.environ, "WINEPREFIX": str(self.prefix), "WINEDEBUG": "-all"}
        self.expected_login = None

    def login(self):
        content = (self.root / "config/common.ini").read_text(encoding="utf-16")
        server = re.search(r"(?m)^Server=(.*)$", content)
        login = re.search(r"(?m)^Login=(\d+)$", content)
        if not server or server[1].strip() != "JustMarkets-Demo6" or not login:
            raise ValueError("Saved JustMarkets-Demo6 account required")
        return login[1]

    def check_charts(self):
        paths = list((self.root / "MQL5/Profiles/Charts").rglob("*.chr"))
        paths += [self.root / "MQL5/Profiles/Templates/default.tpl"]
        for path in paths:
            if not path.exists():
                continue
            data = path.read_bytes()
            content = data.decode("utf-16" if data.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8", errors="replace")
            if re.search(r"<expert\b|expert_name|expertname|^expert=", content, re.I | re.M):
                raise ValueError("An existing chart has an attached expert; automatic startup refused")

    def compile(self, output):
        for name in ("DemoRoundTrip", "DemoSession", "VerifyDemoBatch"):
            shutil.copy2(SOURCE / f"{name}.mq5", self.build / f"{name}.mq5")
        hashes = {}
        for name in ("DemoRoundTrip", "DemoSession", "VerifyDemoBatch"):
            log = self.build / f"{name}_session_compile.log"
            log.unlink(missing_ok=True)
            subprocess.run([str(self.wine), str(self.root / "metaeditor64.exe"),
                            f"/compile:C:\\Goldnix\\{name}.mq5", f"/log:C:\\Goldnix\\{log.name}"],
                           env=self.env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60)
            text = log.read_text(encoding="utf-16")
            if "0 errors, 0 warnings" not in text:
                raise RuntimeError(f"Compilation failed; inspect {log}")
            shutil.copy2(log, output / log.name)
            for suffix in (".mq5", ".ex5"):
                source = self.build / (name + suffix)
                shutil.copy2(source, self.root / "MQL5/Scripts/Goldnix" / source.name)
                shutil.copy2(source, output / "source" / source.name)
                hashes[source.name] = hashlib.sha256(source.read_bytes()).hexdigest()
        return hashes

    def preset(self, filename, values):
        path = self.root / "MQL5/Presets" / filename
        path.write_text("".join(f"{key}={value}\n" for key, value in values.items()))
        path.chmod(0o600)

    def config(self, run, script, preset, enabled):
        path = self.build / f"{run['run_id']}_launch.ini"
        path.write_text(f"[Experts]\nEnabled={int(enabled)}\nAllowLiveTrading={int(enabled)}\nAllowDllImport=0\nAccount=1\nProfile=1\n\n[StartUp]\nScript=Goldnix\\{script}\nScriptParameters={preset}\nSymbol=XAUUSD.c\nPeriod=M5\nShutdownTerminal=0\n")
        return path

    def close(self):
        subprocess.run([str(self.wine), "taskkill", "/IM", "terminal64.exe"], env=self.env,
                       capture_output=True, timeout=20)
        for _ in range(60):
            processes = subprocess.run(["ps", "-axo", "comm"], capture_output=True, text=True).stdout
            if not any(line.strip().endswith("/terminal64.exe") for line in processes.splitlines()):
                return
            time.sleep(.25)
        raise RuntimeError("Terminal did not close gracefully")

    def disable_saved(self):
        path = self.root / "config/common.ini"
        content = path.read_text(encoding="utf-16")
        match = re.search(r"(?ms)^\[Experts\]\n.*?(?=^\[|\Z)", content)
        if not match:
            raise RuntimeError("Missing saved Experts settings")
        section = match[0]
        for key in ("Enabled", "AllowLiveTrading", "AllowDllImport"):
            if re.search(r"(?m)^" + key + "=", section):
                section = re.sub(r"(?m)^" + key + r"=[^\n]*", key + "=0", section)
            else:
                section += key + "=0\n"
        path.write_text(content[:match.start()] + section + content[match.end():], encoding="utf-16")

    def restart(self, config, output, *, disable=False):
        self.close()
        if disable:
            self.disable_saved()
        with (output / "terminal_process.log").open("ab") as log:
            subprocess.Popen([str(self.wine), str(self.root / "terminal64.exe"), f"/config:C:\\Goldnix\\{config.name}"],
                             cwd=self.root, env=self.env, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                             start_new_session=True)

    def verify(self, run, output, label):
        if self.expected_login is None:
            self.expected_login = self.login()
        preset = f"{run['run_id']}_verify.set"
        self.preset(preset, {"VerificationRunId": run["run_id"], "VerificationMagicBase": run["magic_base"],
                             "VerificationMaxTrades": run["max_trades"], "VerificationTimeframe": 5,
                             "VerificationExpectedLogin": self.expected_login})
        paths = {kind: self.common / f"goldnix_batch_{kind}_{run['run_id']}.csv" for kind in ("restore", "history", "bars")}
        for path in paths.values():
            path.unlink(missing_ok=True)
        config = self.config(run, "VerifyDemoBatch", preset, False)
        self.restart(config, output, disable=True)
        for _ in range(100):
            snapshot = {row["key"]: row["value"] for row in rows(paths["restore"])}
            if "net_pnl_usc" in snapshot and paths["history"].exists():
                # The bar export follows the account receipt; allow it to finish.
                time.sleep(2)
                for kind, path in paths.items():
                    if path.exists():
                        shutil.copy2(path, output / f"{label}_{kind}.csv")
                return snapshot, rows(paths["history"])
            time.sleep(1)
        raise RuntimeError("Native read-only verification timed out")

    def recover(self, run, output, index):
        if not 1 <= index <= run["max_trades"]:
            raise ValueError("Invalid recovery index")
        filename = f"{run['run_id']}_recovery.set"
        if not self.expected_login or self.login() != self.expected_login:
            raise ValueError("Account identity changed; recovery refused")
        self.check_charts()
        self.preset(filename, {"ExpectedLogin": self.expected_login, "RunMagic": run["magic_base"] + index,
                              "RunId": f"{run['run_id']}_{index:03}", "HoldSeconds": 300,
                              "RequiredTimeframe": 5, "StopFileName": run["stop_filename"],
                              "CloseOnly": "true", "StopOnInterruption": "true"})
        audit = self.common / f"goldnix_demo_{run['run_id']}_{index:03}.csv"
        previous = len(rows(audit))
        self.restart(self.config(run, "DemoRoundTrip", filename, True), output)
        for _ in range(100):
            fresh = rows(audit)[previous:]
            if any(row["event"] in ("FINAL", "ABORT") for row in fresh):
                return
            time.sleep(1)
        raise RuntimeError("Close-only recovery timed out")


def copy_audits(terminal, run, output):
    for pattern in (f"goldnix_session_{run['run_id']}.csv", f"goldnix_demo_{run['run_id']}_*.csv"):
        for path in terminal.common.glob(pattern):
            shutil.copy2(path, output / path.name)


def save_report(run, output, snapshot, history, reason, initial_balance):
    validate_account(snapshot, flat=True, disabled=True)
    trades = reconcile_history(history, run["magic_base"], run["max_trades"])
    pnl = sum((Decimal(str(trade["pnl_usc"])) for trade in trades), Decimal(0))
    if pnl != Decimal(snapshot["net_pnl_usc"]):
        raise ValueError("Native and independently calculated P&L disagree")
    if any(int(snapshot[key]) != len(trades) for key in ("matching_positions", "entry_deals", "exit_deals")):
        raise ValueError("Native history counts disagree")
    if initial_balance is not None and Decimal(str(initial_balance)) + pnl != Decimal(snapshot["balance_usc"]):
        raise ValueError("Balance changed outside this session; review account history")
    receipt = {"run_id": run["run_id"], "demo_only": True, "method": "M5 timed BUY execution test; no strategy signal",
               "stop_reason": reason, "verified_utc": utc(snapshot["captured_utc_epoch"]),
               "completed": len(trades), "wins": sum(t["pnl_usc"] > 0 for t in trades),
               "losses": sum(t["pnl_usc"] < 0 for t in trades), "net_pnl_usc": float(pnl),
               "net_pnl_usd": float(pnl / 100), "balance_usc": float(snapshot["balance_usc"]),
               "positions": 0, "orders": 0, "automation_enabled": False, "step6_approved": False,
               "trades": trades}
    write_json(output / "RECEIPT.json", receipt)
    with (output / "trades.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(trades[0]) if trades else ["index"])
        writer.writeheader()
        writer.writerows(trades)
    (output / "SUMMARY.md").write_text(
        f"# M5 demo session\n\n{len(trades)} completed 0.01-lot gold trades. "
        f"Net **{float(pnl):+.2f} USC ({float(pnl / 100):+.4f} USD)**. "
        f"Wins: {receipt['wins']}; losses: {receipt['losses']}.\n\n"
        f"Stop reason: {reason}. Balance: {receipt['balance_usc']:.2f} USC. "
        "No open positions or pending orders; automation disabled and verified.\n\n"
        "These are repeated BUY execution tests with a five-minute target exit and broker stop-loss. "
        "They do not validate a trading strategy. Stops can exit earlier; disconnection or sleep can delay local exits. "
        "The loss threshold stops new entries after realized losses and is not a guaranteed loss cap.\n\n"
        "[All trades](trades.csv) · [Receipt](RECEIPT.json) · [History](final_history.csv) · [M5 bars](final_bars.csv)\n")
    return receipt


def controller(output):
    output = Path(output).resolve()
    run = json.loads((output / "SESSION.json").read_text())
    terminal = Terminal()
    lock = (terminal.build / "demo_session.lock").open("a")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    keep_awake = subprocess.Popen(["caffeinate", "-i", "-s", "-w", str(os.getpid())],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    stop = terminal.common / run["stop_filename"]
    def request_stop(signum, frame):
        if not stop.exists():
            stop.write_text(f"Worker received signal {signum}; close and reconcile")
    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    session = terminal.common / f"goldnix_session_{run['run_id']}.csv"
    initial_balance = None
    reason = "preflight"
    launched = False
    try:
        marker = output / "STARTED"
        with marker.open("x") as handle:
            handle.write(utc())
        write_json(output / "STATUS.json", {"state": "preflight", "updated_utc": utc()})
        terminal.expected_login = terminal.login()
        terminal.check_charts()
        snapshot, history = terminal.verify(run, output, "preflight")
        validate_account(snapshot, flat=True, disabled=True)
        if history:
            raise ValueError("Run identifier already has broker history")
        initial_balance = snapshot["balance_usc"]
        if stop.exists():
            raise ValueError("Stop requested before startup")
        if run.get("check_only"):
            # Exercise native stop handling and automatic cleanup without entries.
            stop.write_text("Native stop-control integration check; do not place orders")
        lid = subprocess.run(["ioreg", "-r", "-k", "AppleClamshellState", "-d", "4"], capture_output=True, text=True).stdout
        if re.search(r'"AppleClamshellState"\s*=\s*Yes', lid):
            raise ValueError("Mac lid is closed")
        preset = f"{run['run_id']}_execute.set"
        if terminal.login() != terminal.expected_login:
            raise ValueError("Account changed after preflight")
        terminal.check_charts()
        terminal.preset(preset, {"ExpectedLogin": terminal.expected_login, "RunMagic": run["magic_base"],
                                 "RunId": run["run_id"], "HoldSeconds": 300, "RequiredTimeframe": 5,
                                 "StopFileName": run["stop_filename"], "CloseOnly": "false",
                                 "StopOnInterruption": "true", "SessionSeconds": run["seconds"],
                                 "MaxTrades": run["max_trades"], "LossLimitUSC": run["loss_limit_usc"]})
        for name, digest in run["compiled_sha256"].items():
            if hashlib.sha256((terminal.root / "MQL5/Scripts/Goldnix" / name).read_bytes()).hexdigest() != digest:
                raise ValueError("Installed script changed since preparation")
        terminal.restart(terminal.config(run, "DemoSession", preset, True), output)
        launched = True
        launch_time = time.time()
        deadline = launch_time + run["seconds"] + 60
        last_loop = time.time()
        last_event = launch_time
        while True:
            now = time.time()
            if now - last_loop > 30:
                reason = "host_paused_or_controller_delayed"
                stop.write_text(reason)
            last_loop = now
            events = rows(session)
            starts = [row for row in events if row["event"] == "SESSION_START"]
            if starts:
                deadline = int(fields(starts[0])["deadline_utc_epoch"])
            done = [row for row in events if row["event"] == "TRADE_COMPLETE"]
            endings = [row for row in events if row["event"] in ("SESSION_END", "ABORT")]
            audits = list(terminal.common.glob(f"goldnix_demo_{run['run_id']}_*.csv"))
            for path in [session, *audits]:
                if path.exists():
                    last_event = max(last_event, path.stat().st_mtime)
            state = "stopping" if stop.exists() else "running"
            status = {"state": state, "run_id": run["run_id"], "updated_utc": utc(),
                      "deadline_utc": utc(deadline), "completed": len(done),
                      "net_pnl_usc": float(fields(done[-1])["cumulative_pnl_usc"]) if done else 0,
                      "controller_pid": os.getpid(), "background_job": run["job_label"]}
            write_json(output / "STATUS.json", status)
            copy_audits(terminal, run, output)
            if endings:
                reason = fields(endings[-1]).get("reason", endings[-1]["details"])
                break
            if now >= deadline:
                reason = "time_limit"
                if not stop.exists():
                    stop.write_text(reason)
            if now - last_event > 90:
                reason = "native_heartbeat_stale"
                stop.write_text(reason)
                break
            if stop.exists() and now - stop.stat().st_mtime > 90:
                break
            time.sleep(2)
    except Exception as exc:
        reason = f"controller_error: {exc}"
        write_json(output / "ERROR.json", {"error": str(exc), "utc": utc()})
    finally:
        stop.write_text(reason)
        write_json(output / "STATUS.json", {"state": "reconciling", "reason": reason, "updated_utc": utc()})
        try:
            if launched:
                # A read-only restart ends the native loop; the persistent stop file
                # and session marker prohibit additional entries on any retry.
                snapshot, history = terminal.verify(run, output, "initial_final")
                for attempt in range(3):
                    if snapshot.get("connected") == "1":
                        validate_account(snapshot)
                        if snapshot.get("positions") == "0" and snapshot.get("orders") == "0":
                            break
                        starts = [fields(row) for row in rows(session) if row["event"] == "TRADE_START"]
                        if not starts:
                            raise ValueError("Unowned position; no recovery entry identifier")
                        terminal.recover(run, output, int(starts[-1]["index"]))
                    else:
                        time.sleep(10)
                    snapshot, history = terminal.verify(run, output, f"recovery_{attempt}")
            else:
                snapshot, history = terminal.verify(run, output, "initial_final")
            validate_account(snapshot, flat=True, disabled=True)
            # Preserve the exact verified snapshot/history under stable report names.
            for kind in ("restore", "history", "bars"):
                path = terminal.common / f"goldnix_batch_{kind}_{run['run_id']}.csv"
                if path.exists():
                    shutil.copy2(path, output / f"final_{kind}.csv")
            copy_audits(terminal, run, output)
            receipt = save_report(run, output, snapshot, history, reason, initial_balance)
            write_json(output / "STATUS.json", {"state": "verified_complete", "updated_utc": utc(),
                                                 **{key: receipt[key] for key in ("completed", "net_pnl_usc", "balance_usc", "stop_reason", "positions", "orders", "automation_enabled")}})
        except Exception as exc:
            write_json(output / "STATUS.json", {"state": "needs_reconciliation", "updated_utc": utc(),
                                                 "reason": reason, "error": str(exc), "new_entries_blocked": True})
            # Best effort leaves the startup configuration read-only even offline.
            try:
                terminal.config(run, "VerifyDemoBatch", f"{run['run_id']}_verify.set", False)
            except Exception:
                pass
        for suffix in ("execute", "recovery", "verify"):
            (terminal.root / "MQL5/Presets" / f"{run['run_id']}_{suffix}.set").unlink(missing_ok=True)
        keep_awake.terminate()
        write_json(output / "MANIFEST.json", {"algorithm": "sha256", "files": {
            str(path.relative_to(output)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(output.rglob("*")) if path.is_file()
            and path.name not in ("MANIFEST.json", "controller.stdout.log", "controller.stderr.log", "terminal_process.log")
            and not path.name.endswith(".tmp")}})


def prepare(minutes, *, check_only=False):
    if not math.isfinite(minutes) or not 6 <= minutes <= 180:
        raise ValueError("Choose 6–180 minutes")
    now = datetime.now(timezone.utc)
    run_id = "M5_" + now.strftime("%Y%m%dT%H%M%SZ")
    output = SOURCE / "out" / ("demo_session_" + run_id)
    (output / "source").mkdir(parents=True, exist_ok=False)
    terminal = Terminal()
    hashes = terminal.compile(output)
    shutil.copy2(__file__, output / "source/demo_session.py")
    run = {"run_id": run_id, "created_utc": utc(), "seconds": int(minutes * 60), "max_trades": 36,
           "magic_base": int(now.timestamp()) * 1000, "timeframe": "M5", "symbol": "XAUUSD.c",
           "volume_lots": .01, "hold_seconds": 300, "loss_limit_usc": 20.0,
           "stop_filename": f"goldnix_session_{run_id}.stop", "compiled_sha256": hashes,
           "check_only": check_only,
           "job_label": f"local.goldnix.demo.{run_id.lower()}", "method": "timed BUY execution test; no strategy signal"}
    write_json(output / "SESSION.json", run)
    write_json(output / "STATUS.json", {"state": "prepared", "run_id": run_id})
    return output


def start(output):
    output = Path(output).resolve()
    run = json.loads((output / "SESSION.json").read_text())
    if (output / "STARTED").exists():
        raise ValueError("Session already attempted; no relaunch of new entries")
    # launchd owns the worker independently of this chat or terminal shell.
    plist = {"Label": run["job_label"], "ProgramArguments": [sys.executable, str(output / "source/demo_session.py"), "_worker", str(output)],
             "WorkingDirectory": str(SOURCE.parent), "RunAtLoad": True, "KeepAlive": False,
             "StandardOutPath": str(output / "controller.stdout.log"),
             "StandardErrorPath": str(output / "controller.stderr.log"), "ProcessType": "Background"}
    path = output / "controller.plist"
    path.write_bytes(plistlib.dumps(plist))
    subprocess.run(["launchctl", "bootstrap", f"gui/{os.getuid()}", str(path)], check=True, capture_output=True)
    if not run.get("check_only"):
        write_json(output.parent / "LATEST_SESSION.json", {"run_id": run["run_id"], "output": str(output),
                                                           "status": str(output / "STATUS.json"),
                                                           "receipt": str(output / "RECEIPT.json")})
    return {"started": True, "job_label": run["job_label"], "output": str(output)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "start", "status", "stop", "_worker"))
    parser.add_argument("output", nargs="?")
    parser.add_argument("--minutes", type=float, default=180)
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    if args.command == "prepare":
        print(prepare(args.minutes, check_only=args.check_only))
        return
    if not args.output:
        parser.error("output path required")
    output = Path(args.output).resolve()
    if args.command == "start":
        print(json.dumps(start(output)))
    elif args.command == "status":
        print((output / "STATUS.json").read_text())
    elif args.command == "stop":
        run = json.loads((output / "SESSION.json").read_text())
        (Terminal().common / run["stop_filename"]).write_text("User requested stop")
        print("Stop requested; current own position will be closed/reconciled, then automation disabled.")
    else:
        controller(output)


if __name__ == "__main__":
    main()
