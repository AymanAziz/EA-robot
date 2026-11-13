"""Stage, verify and activate the explicitly requested experimental DEMO variant."""

from datetime import UTC, datetime
import csv
import hashlib
import json
import re
import shutil
import subprocess
import time

from goldnix_venue.demo_session import Terminal
from goldnix_auto_m1.ops import close_terminal, status, truth
from .build_source import generate, HERE

OUT = HERE / "out"


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")


def public(s):
    keys = (
        "captured_utc",
        "program",
        "version",
        "timeframe",
        "signal_timeframe",
        "context_timeframes",
        "candle_clock",
        "qualification",
        "step6",
        "step7",
        "identity_matches",
        "connected",
        "data_ready",
        "trade_permission",
        "daily_attempts",
        "daily_r",
        "daily_loss_halt",
        "audit_halt",
        "state_broken",
        "balance_usc",
        "positions",
        "orders",
        "pending_magic",
        "last_decision",
        "exclusive_lock_verified",
        "warmup_m5_bars",
        "h4_complete_bars",
        "h4_ready",
        "h4_direction",
    )
    return {k: s[k] for k in keys if k in s}


def flat(s):
    return all(s.get(k) == "0" for k in ("positions", "orders", "pending_magic"))


def compile_staged():
    t = Terminal()
    stage = t.build / "D01Native"
    generate(stage)
    shutil.copy2(HERE / "MtfProbe.mq5", stage / "MtfProbe.mq5")
    result = {}
    for name in ("GoldnixMTFDemo", "MtfProbe"):
        log = stage / f"{name}.log"
        log.unlink(missing_ok=True)
        subprocess.run(
            [
                str(t.wine),
                str(t.root / "metaeditor64.exe"),
                f"/compile:C:\\Goldnix\\D01Native\\{name}.mq5",
                f"/log:C:\\Goldnix\\D01Native\\{name}.log",
            ],
            env=t.env,
            capture_output=True,
            timeout=90,
            check=False,
        )
        content = log.read_text(encoding="utf-16")
        OUT.mkdir(exist_ok=True)
        (OUT / f"{name}.compile.log").write_text(content)
        if "0 errors, 0 warnings" not in content:
            print(content)
            raise RuntimeError("Native compile failed")
        result[name] = hashlib.sha256((stage / f"{name}.ex5").read_bytes()).hexdigest()
    write(OUT / "COMPILED.json", result)
    return result


def launch(t, config, output):
    with (output / "terminal_process.log").open("ab") as log:
        subprocess.Popen(
            [str(t.wine), str(t.root / "terminal64.exe"), f"/config:C:\\Goldnix\\{config.name}"],
            cwd=t.root,
            env=t.env,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=log,
            start_new_session=True,
        )


def activate():
    t = Terminal()
    login = t.login()
    before = status()
    if (
        time.time() - int(before.get("captured_utc", 0)) > 15
        or not truth(before.get("identity_matches"))
        or not flat(before)
    ):
        raise ValueError("Fresh verified flat demo required")
    compiled = json.loads((OUT / "COMPILED.json").read_text())
    reference_checks = json.loads((OUT / "REFERENCE_CHECKS.json").read_text())
    if len(reference_checks) != 4 or not all(r["passed"] for r in reference_checks):
        raise ValueError("Independent feature reference checks required")
    stage = t.build / "D01Native"
    for name, expected in compiled.items():
        if hashlib.sha256((stage / f"{name}.ex5").read_bytes()).hexdigest() != expected:
            raise ValueError("Staged binary changed")
    run_id = datetime.now(UTC).strftime("D01_%Y%m%dT%H%M%SZ")
    private = HERE.parent / "var/goldnix_d01_private" / run_id
    private.mkdir(parents=True, mode=0o700)
    output = OUT / run_id
    output.mkdir()
    write(output / "BEFORE.json", public(before))
    write(OUT / "LATEST.json", {"output": str(output), "private": str(private)})
    close_terminal(t)
    stopped = status()
    if not flat(stopped):
        subprocess.Popen(["open", "-a", "MetaTrader 5"])
        raise ValueError("Exposure appeared during handoff; terminal reopened")
    profile = t.root / "MQL5/Profiles/Charts/Default"
    common = t.root / "config/common.ini"
    shutil.copytree(profile, private / "profile")
    shutil.copy2(common, private / "common.ini")
    installed_before = t.root / "MQL5/Experts/GoldnixD01"
    if installed_before.exists():
        shutil.copytree(installed_before, private / "expert_before")
    shutil.copy2(t.root / "MQL5/Files/GoldnixAutoM5Demo/state.csv", private / "state_at_handoff.csv")
    try:
        # Native policy script has no order API and runs while trading is disabled.
        target = t.root / "MQL5/Scripts/GoldnixD01"
        target.mkdir(exist_ok=True)
        shutil.copy2(stage / "MtfProbe.ex5", target / "MtfProbe.ex5")
        shutil.copy2(OUT / "native_fixture.csv", t.common / "goldnix_d01_fixture.csv")
        t.disable_saved()
        config = t.build / "D01Probe.ini"
        config.write_text(
            "[Experts]\nEnabled=0\nAllowLiveTrading=0\nAllowDllImport=0\n\n[StartUp]\nScript=GoldnixD01\\MtfProbe\nSymbol=XAUUSD.c\nPeriod=M1\nShutdownTerminal=0\n"
        )
        started = time.time()
        launch(t, config, output)
        receipt = t.common / "goldnix_d01_policy.csv"
        while time.time() - started < 120:
            if receipt.exists() and receipt.stat().st_mtime >= started:
                break
            time.sleep(1)
        else:
            raise TimeoutError("Native policy probe output missing")
        with receipt.open() as file:
            rows = list(csv.DictReader(file))
        if len(rows) != 1 or rows[0]["failed"] != "0" or int(rows[0]["passed"]) < 4814:
            raise ValueError("Native policy probe failed")
        write(output / "NATIVE_POLICY.json", rows[0])
        import pandas as pd
        from .verify import compare

        actual = pd.read_csv(t.common / "goldnix_d01_features.csv")
        reference = compare(pd.read_csv(OUT / "fixture_bars.csv"), actual)
        write(output / "NATIVE_FEATURES.json", reference)
        print(json.dumps({"native_policy": rows[0]}), flush=True)
        close_terminal(t)
        # Restore saved configuration before a precise one-chart expert replacement.
        shutil.copytree(private / "profile", profile, dirs_exist_ok=True)
        shutil.copy2(private / "common.ini", common)
        charts = list(profile.glob("*.chr"))
        matched = []
        for chart in charts:
            text = chart.read_text(encoding="utf-16")
            if "<expert>" in text:
                if (
                    not any(name in text for name in ("GoldnixAutoM1", "GoldnixMTFDemo"))
                    or "symbol=XAUUSD.c" not in text
                    or "period_size=1\n" not in text
                ):
                    raise ValueError("Unexpected saved expert/chart")
                matched.append((chart, text))
        if len(matched) != 1:
            raise ValueError("Exactly one recognized M1 expert chart required")
        chart, text = matched[0]
        expert = re.search(r"<expert>.*?</expert>", text, re.S)
        if expert is None or f"ExpectedLogin={login}" not in expert[0]:
            raise ValueError("Saved expert account mismatch")
        changed = (
            expert[0]
            .replace("GoldnixAutoM1", "GoldnixMTFDemo")
            .replace("Goldnix\\GoldnixMTFDemo", "GoldnixD01\\GoldnixMTFDemo")
        )
        changed = re.sub(r"(?m)^ExecutionCheckRequestUtc=.*\n", "", changed)
        changed = re.sub(r"(?m)^EnableDemoTrading=.*$", "EnableDemoTrading=true", changed)
        if "GoldnixD01" not in changed:
            raise ValueError("Expert path not replaced")
        target = t.root / "MQL5/Experts/GoldnixD01"
        target.mkdir(exist_ok=True)
        for source in stage.iterdir():
            if source.suffix in (".mqh", ".mq5", ".ex5"):
                shutil.copy2(source, target / source.name)
        chart.write_text(text[: expert.start()] + changed + text[expert.end() :], encoding="utf-16")
        # Normal application reopen uses the saved chart; no temporary startup EA.
        subprocess.run(["open", "-a", "MetaTrader 5"], check=True)
        write(
            output / "ACTIVATION.json",
            {
                "installed": True,
                "experimental": True,
                "expected_program": "GoldnixMTFDemo",
                "compiled": compiled,
                "risk_at_handoff": public(stopped),
                "no_risk_checkpoint_restored": True,
            },
        )
        print(
            json.dumps({"demo_experimental_installed": True, "warmup_pending": True, "output": str(output)}),
            flush=True,
        )
        return output
    except BaseException:
        close_terminal(t)
        shutil.copytree(private / "profile", profile, dirs_exist_ok=True)
        shutil.copy2(private / "common.ini", common)
        if (private / "expert_before").exists():
            shutil.copytree(private / "expert_before", installed_before, dirs_exist_ok=True)
        subprocess.run(["open", "-a", "MetaTrader 5"], check=False)
        raise


if __name__ == "__main__":
    import sys

    if sys.argv[1] == "compile":
        print(json.dumps(compile_staged()))
    elif sys.argv[1] == "activate":
        activate()
    elif sys.argv[1] == "status":
        print(json.dumps(public(status()), indent=2))
