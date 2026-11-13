"""Run isolated strategy replay, then restore the verified flat demo terminal."""

import argparse
import csv
from datetime import UTC, datetime, timedelta
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import time
from zoneinfo import ZoneInfo

from goldnix_venue.demo_session import Terminal
from goldnix_auto_m1.ops import close_terminal, status, truth, wait_ready
from goldnix_auto_m1.protection_validation import flat, selected
from .native_adapter import generate, HERE


def write(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")


def validate_period(start, end):
    if not "2023.01.01" <= start < end <= "2026.01.01":
        raise ValueError("Native engineering replay restricted to pre-holdout 2023–2025")
    current = datetime.strptime(start, "%Y.%m.%d").replace(tzinfo=UTC)
    finish = datetime.strptime(end, "%Y.%m.%d").replace(tzinfo=UTC)
    while current < finish:
        if (current + timedelta(hours=12)).astimezone(
            ZoneInfo("Europe/Helsinki")
        ).utcoffset().total_seconds() != 7200:
            raise ValueError(
                "Fixed +7200 offset only supports winter windows; DST requires a separately validated adapter"
            )
        current += timedelta(days=1)


def run(start, end, *, timeout=1800):
    validate_period(start, end)
    t = Terminal()
    t.login()  # Verify the saved demo account without disclosing its login.
    before = status()
    if (
        time.time() - int(before.get("captured_utc", 0)) > 10
        or not truth(before.get("identity_matches"))
        or not flat(before)
    ):
        raise ValueError("Fresh verified flat demo required; no open trade may be interrupted")
    run_id = datetime.now(UTC).strftime("P01N_%Y%m%dT%H%M%SZ")
    output = HERE / "out" / run_id
    output.mkdir(parents=True)
    write(output / "BEFORE.json", selected(before))
    stage = t.build / "P01Native"
    manifest = generate(stage)
    log = t.build / "P01NativeCompile.log"
    log.unlink(missing_ok=True)
    subprocess.run(
        [
            str(t.wine),
            str(t.root / "metaeditor64.exe"),
            "/compile:C:\\Goldnix\\P01Native\\P01NativeReplay.mq5",
            "/log:C:\\Goldnix\\P01NativeCompile.log",
        ],
        env=t.env,
        capture_output=True,
        timeout=60,
    )
    result = log.read_text(encoding="utf-16")
    (output / "compile.log").write_text(result)
    if "0 errors, 0 warnings" not in result:
        raise RuntimeError("Native compile failed")
    shutil.copytree(stage, output / "SOURCE")
    target = t.root / "MQL5/Experts/GoldnixP01Test"
    target.mkdir(exist_ok=True)
    shutil.copy2(stage / "P01NativeReplay.ex5", target / "P01NativeReplay.ex5")
    manifest["ex5_sha256"] = hashlib.sha256((target / "P01NativeReplay.ex5").read_bytes()).hexdigest()
    write(output / "ADAPTER_MANIFEST.json", manifest)
    preset = t.root / "MQL5/Profiles/Tester" / f"{run_id}.set"
    preset.write_text(
        f"ReplayRunId={run_id}\nReplayOffsetSeconds=7200\nExpectedLogin=1\nEnableDemoTrading=true\nExecutionCheckRequestUtc=0\n"
    )
    config = t.build / f"{run_id}.ini"
    config.write_text(
        "[Experts]\nEnabled=0\nAllowLiveTrading=0\nAllowDllImport=0\n\n[Tester]\n"
        "Expert=GoldnixP01Test\\P01NativeReplay.ex5\n"
        f"ExpertParameters={preset.name}\nSymbol=XAUUSD.c\nPeriod=M1\nModel=0\nExecutionMode=0\nOptimization=0\n"
        f"FromDate={start}\nToDate={end}\nForwardMode=0\nDeposit=20\nCurrency=USD\nLeverage=1:100\n"
        "UseLocal=1\nUseRemote=0\nUseCloud=0\nVisual=0\nShutdownTerminal=1\n"
    )
    shutil.copy2(config, output / "tester.ini")
    write(HERE / "LATEST.json", {"output": str(output)})
    private = HERE.parent / "var/goldnix_p01_private" / run_id
    private.mkdir(parents=True, mode=0o700)
    stopped = False
    backed_up = False
    try:
        close_terminal(t)
        stopped = True
        if not flat(status()):
            raise RuntimeError("Exposure appeared during handoff; restore terminal immediately")
        shutil.copy2(t.root / "config/common.ini", private / "common.ini")
        shutil.copytree(t.root / "MQL5/Profiles/Charts/Default", private / "Default")
        state_path = t.root / "MQL5/Files/GoldnixAutoM5Demo/state.csv"
        shutil.copy2(state_path, private / "state.csv")
        backed_up = True
        t.disable_saved()
        with (output / "terminal_process.log").open("ab") as stream:
            subprocess.Popen(
                [str(t.wine), str(t.root / "terminal64.exe"), f"/config:C:\\Goldnix\\{config.name}"],
                cwd=t.root,
                env=t.env,
                stdin=subprocess.DEVNULL,
                stdout=stream,
                stderr=stream,
                start_new_session=True,
            )
        write(
            output / "STARTED.json",
            {
                "run_id": run_id,
                "start": start,
                "end_exclusive": end,
                "model": "generated broker M1 ticks",
                "formal_qualification": False,
                "started_utc": datetime.now(UTC).isoformat(),
            },
        )
        print(json.dumps({"tester_started": run_id, "output": str(output)}), flush=True)
        deadline = time.monotonic() + timeout
        result_path = None
        while time.monotonic() < deadline:
            found = list(
                (t.prefix / "drive_c/users").glob(
                    f"*/AppData/Roaming/MetaQuotes/Terminal/Common/Files/P01Replay_{run_id}/receipt.csv"
                )
            )
            if len(found) > 1:
                raise RuntimeError("Ambiguous tester receipt")
            if found:
                result_path = found[0].parent
                break
            time.sleep(2)
        if result_path is None:
            raise TimeoutError("Native run timed out; retain diagnostic files")
        time.sleep(2)
        close_terminal(t)
        shutil.copytree(result_path, output / "native")
        receipt = dict(csv.reader((output / "native/receipt.csv").open()))
        write(output / "NATIVE_RESULT.json", receipt)
        print(json.dumps({"native_complete": receipt}), flush=True)
    finally:
        if stopped:
            close_terminal(t)
            if backed_up:
                shutil.copy2(state_path, private / "state_after.csv")
                keys = [
                    "version",
                    "owner",
                    "sequence",
                    "day",
                    "attempts",
                    "base_equity",
                    "realized_r",
                    "daily_halt",
                    "fatal",
                    "recover",
                    "last_signal",
                    "last_exit_bar",
                    "pending_magic",
                    "pending_server",
                    "pending_direction",
                    "pending_atr",
                    "pending_distance",
                    "position_id",
                    "fatal_reason",
                ]
                first = list(csv.reader((private / "state.csv").open()))[0][1].split("|")
                last = list(csv.reader(state_path.open()))[0][1].split("|")
                changes = [key for key, a, b in zip(keys, first, last) if a != b]
                write(
                    output / "CHECKPOINT_AUDIT.json",
                    {
                        "changed_fields": changes,
                        "risk_fields_preserved": len(first) == len(last) == 19
                        and all(k in ("sequence", "last_signal") for k in changes),
                        "note": "Capture-only production chart may advance sequence and last_signal during tester run. Never restore an older risk checkpoint.",
                    },
                )
                shutil.copy2(private / "common.ini", t.root / "config/common.ini")
                shutil.copytree(
                    private / "Default", t.root / "MQL5/Profiles/Charts/Default", dirs_exist_ok=True
                )
            reopened = time.time()
            subprocess.run(["open", "-a", str(Path.home() / "Applications/MetaTrader 5.app")], check=True)
            current = wait_ready(previous_folder=before.get("run_folder"), started=int(reopened))
            restored = selected(current)
            restored["risk_state_preserved"] = all(
                current.get(k) == before.get(k)
                for k in ("daily_attempts", "daily_r", "balance_usc", "pending_magic")
            )
            write(output / "RESTORED.json", restored)
            print(json.dumps({"demo_restored": restored}), flush=True)
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default="2024.02.01")
    parser.add_argument("--end", default="2024.02.03")
    args = parser.parse_args()
    run(args.start, args.end)
