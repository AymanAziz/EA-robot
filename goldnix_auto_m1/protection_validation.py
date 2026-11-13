"""Bounded native checks and deployment of the user-authorized DEMO protection update."""

import argparse
import csv
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import time

from goldnix_venue.demo_session import Terminal, write_json
from .ops import HERE, DEPLOY, close_terminal, status, truth

BACKUP = DEPLOY / "before_profit_protection"
PRIVATE = DEPLOY / "private_profit_protection"
RUN = DEPLOY / "profit_protection_validation"


def selected(s):
    keys = (
        "version",
        "captured_utc",
        "run_folder",
        "identity_matches",
        "connected",
        "data_ready",
        "trade_permission",
        "positions",
        "orders",
        "daily_attempts",
        "daily_r",
        "pending_magic",
        "balance_usc",
        "audit_halt",
        "state_broken",
        "profit_protection_enabled",
        "profit_protection_state",
    )
    return {k: s.get(k) for k in keys}


def flat(s):
    return s.get("positions") == "0" and s.get("orders") == "0" and s.get("pending_magic") == "0"


def prepare():
    t = Terminal()
    t.login()
    before = status()
    if (
        time.time() - int(before.get("captured_utc", 0)) > 10
        or not truth(before.get("identity_matches"))
        or not flat(before)
    ):
        raise ValueError("Fresh verified flat demo required for test handoff")
    if BACKUP.exists() or PRIVATE.exists():
        raise ValueError("Preserve existing backup; preparation already performed")
    close_terminal(t)
    after = status()
    if not flat(after):
        raise ValueError("Exposure appeared before terminal stop; retain server SL/TP and reconcile")
    BACKUP.mkdir()
    PRIVATE.mkdir(mode=0o700)
    RUN.mkdir(exist_ok=False)
    for folder in ("Experts", "Scripts"):
        source = t.root / "MQL5" / folder / "Goldnix"
        for name in (
            "GoldnixAutoM1.mq5",
            "GoldnixAutoM1.ex5",
            "AutoM1Policy.mqh",
            "AutoM1PolicyProbe.mq5",
            "AutoM1PolicyProbe.ex5",
        ):
            if (source / name).exists():
                target = BACKUP / folder
                target.mkdir(exist_ok=True)
                shutil.copy2(source / name, target / name)
    for name in ("VERIFIED.json", "COMPILED.json", "SIGNAL_CHECK.json"):
        if (DEPLOY / name).exists():
            shutil.copy2(DEPLOY / name, BACKUP / name)
    shutil.copy2(t.root / "config/common.ini", PRIVATE / "common.ini")
    shutil.copytree(t.root / "MQL5/Profiles/Charts/Default", PRIVATE / "Default")
    shutil.copy2(t.root / "MQL5/Files/GoldnixAutoM5Demo/state.csv", PRIVATE / "state_before.csv")
    write_json(RUN / "BEFORE.json", selected(after))
    print(json.dumps({"prepared_flat": True, "daily_attempts_preserved": after["daily_attempts"]}))


def install_artifact(t, name, kind):
    target = t.root / "MQL5" / kind / "Goldnix"
    target.mkdir(parents=True, exist_ok=True)
    for header in HERE.glob("*.mqh"):
        shutil.copy2(header, target / header.name)
    for ext in ("mq5", "ex5"):
        shutil.copy2(t.build / f"{name}.{ext}", target / f"{name}.{ext}")


def policy():
    if not (RUN / "BEFORE.json").exists():
        raise ValueError("Prepare flat handoff first")
    t = Terminal()
    install_artifact(t, "AutoM1PolicyProbe", "Scripts")
    config = t.build / "ProfitPolicy_readonly.ini"
    config.write_text(
        "[Experts]\nEnabled=0\nAllowLiveTrading=0\nAllowDllImport=0\n\n[StartUp]\nScript=Goldnix\\AutoM1PolicyProbe\nSymbol=XAUUSD.c\nPeriod=M1\nShutdownTerminal=0\n"
    )
    write_json(RUN / "POLICY_STARTED.json", {"epoch": time.time()})
    t.restart(config, RUN, disable=True)
    print(json.dumps({"native_policy_started": True, "demo_trading_disabled_during_checks": True}))


def policy_result():
    t = Terminal()
    path = t.root / "MQL5/Files/goldnix_auto_m1_policy_probe.csv"
    started = json.loads((RUN / "POLICY_STARTED.json").read_text())["epoch"]
    if not path.exists() or path.stat().st_mtime < started:
        print(json.dumps({"pending": True}))
        return
    records = list(csv.DictReader(path.open()))
    if len(records) != 1 or int(records[0]["failed"]) or int(records[0]["passed"]) < 78:
        raise ValueError(f"Native policy checks failed: {records}")
    write_json(RUN / "POLICY_RESULT.json", records[0])
    print(json.dumps(records[0]))


def tester():
    if not (RUN / "POLICY_RESULT.json").exists():
        raise ValueError("Native policy checks required")
    t = Terminal()
    close_terminal(t)
    install_artifact(t, "ProfitBrokerProbe", "Experts")
    run_id = datetime.now(UTC).strftime("P01_%Y%m%dT%H%M%SZ")
    preset = t.root / "MQL5/Profiles/Tester" / f"{run_id}.set"
    preset.parent.mkdir(parents=True, exist_ok=True)
    preset.write_text(f"RunId={run_id}\n")
    (t.root / "reports/GoldnixProfit").mkdir(parents=True, exist_ok=True)
    config = t.build / f"{run_id}.ini"
    config.write_text(
        "[Experts]\nEnabled=0\nAllowLiveTrading=0\nAllowDllImport=0\n\n[Tester]\nExpert=Goldnix\\ProfitBrokerProbe.ex5\n"
        f"ExpertParameters={preset.name}\nSymbol=XAUUSD.c\nPeriod=M1\nModel=0\nExecutionMode=0\nOptimization=0\n"
        "FromDate=2024.02.01\nToDate=2024.02.03\nForwardMode=0\nDeposit=20\nCurrency=USD\nLeverage=1:100\n"
        f"UseLocal=1\nUseRemote=0\nUseCloud=0\nVisual=0\nReport=reports\\GoldnixProfit\\{run_id}.htm\nReplaceReport=0\nShutdownTerminal=1\n"
    )
    write_json(
        RUN / "TESTER_STARTED.json",
        {
            "run_id": run_id,
            "epoch": time.time(),
            "model": "generated ticks from broker M1",
            "fault_injection": True,
            "profitability_test": False,
        },
    )
    shutil.copy2(config, RUN / f"{run_id}.ini")
    t.restart(config, RUN, disable=True)
    print(json.dumps({"tester_started": run_id}))


def tester_result():
    t = Terminal()
    run_id = json.loads((RUN / "TESTER_STARTED.json").read_text())["run_id"]
    paths = list(
        (t.prefix / "drive_c/users").glob(
            f"*/AppData/Roaming/MetaQuotes/Terminal/Common/Files/GoldnixProfitProbe_{run_id}_result.csv"
        )
    )
    if not paths:
        print(json.dumps({"pending": True}))
        return
    if len(paths) != 1:
        raise ValueError("Ambiguous native result")
    result = list(csv.DictReader(paths[0].open()))
    if len(result) != 1:
        raise ValueError("Invalid tester receipt")
    result = result[0]
    for key in (
        "passed",
        "failed",
        "attempts",
        "buy_modifications",
        "sell_modifications",
        "restart_checks",
        "injected_rejections",
        "floor_closes",
    ):
        result[key] = int(result[key])
    result["coverage_passed"] = (
        result["failed"] == 0
        and result["buy_modifications"] > 0
        and result["sell_modifications"] > 0
        and result["restart_checks"] >= 2
        and result["injected_rejections"] == 2
        and result["floor_closes"] >= 2
    )
    write_json(RUN / f"{run_id}_RESULT.json", result)
    shutil.copy2(paths[0].with_name(f"GoldnixProfitProbe_{run_id}_events.csv"), RUN / f"{run_id}_events.csv")
    print(json.dumps(result))
    if not result["coverage_passed"]:
        raise ValueError("Native broker-path validation failed or coverage insufficient")
    write_json(RUN / "TESTER_RESULT.json", result)


def activate():
    result = json.loads((RUN / "TESTER_RESULT.json").read_text())
    if not result["coverage_passed"]:
        raise ValueError("Tester coverage required")
    t = Terminal()
    close_terminal(t)
    before = json.loads((RUN / "BEFORE.json").read_text())
    state = list(csv.reader((t.root / "MQL5/Files/GoldnixAutoM5Demo/state.csv").open()))[0][1].split("|")
    if state[4] != before["daily_attempts"] or state[12] != "0":
        raise ValueError("Daily attempts changed or pending exposure; reconcile before activation")
    staged = json.loads((DEPLOY / "STAGED.json").read_text())
    for name, expected in staged.items():
        source = HERE / Path(name).name if name.endswith(".mqh") else t.build / Path(name).name
        if hashlib.sha256(source.read_bytes()).hexdigest() != expected:
            raise ValueError("Staged source/binary changed; recompile and revalidate")
    profile = t.root / "MQL5/Profiles/Charts/Default"
    shutil.copytree(profile, PRIVATE / "AfterTestsDefault", dirs_exist_ok=True)
    shutil.rmtree(profile)
    shutil.copytree(PRIVATE / "Default", profile)
    shutil.copy2(PRIVATE / "common.ini", t.root / "config/common.ini")
    for name, kind in (
        ("GoldnixAutoM1", "Experts"),
        ("AutoM1PolicyProbe", "Scripts"),
        ("ProfitBrokerProbe", "Experts"),
    ):
        install_artifact(t, name, kind)
    write_json(DEPLOY / "COMPILED.json", staged)
    write_json(RUN / "ACTIVATION_STARTED.json", {"epoch": time.time(), "version": "1.20"})
    subprocess.run(["open", "-a", str(Path.home() / "Applications/MetaTrader 5.app")], check=True)
    print(json.dumps({"normal_app_started": True, "version": "1.20"}))


def active_result():
    s = status()
    before = json.loads((RUN / "BEFORE.json").read_text())
    started = json.loads((RUN / "ACTIVATION_STARTED.json").read_text())["epoch"]
    if (
        time.time() - int(s.get("captured_utc", 0)) > 10
        or int(s.get("captured_utc", 0)) < started
        or not truth(s.get("data_ready"))
    ):
        print(json.dumps({"pending": True, "state": s.get("state")}))
        return
    if (
        s.get("version") != "1.20"
        or not all(
            truth(s.get(k))
            for k in ("identity_matches", "connected", "trade_permission", "profit_protection_enabled")
        )
        or truth(s.get("audit_halt"))
        or truth(s.get("state_broken"))
        or int(s["daily_attempts"]) < int(before["daily_attempts"])
    ):
        raise ValueError("Active protection validation failed")
    write_json(RUN / "ACTIVE.json", selected(s))
    print(json.dumps(selected(s)))


if __name__ == "__main__":
    commands = {
        "prepare": prepare,
        "policy": policy,
        "policy-result": policy_result,
        "tester": tester,
        "tester-result": tester_result,
        "activate": activate,
        "active-result": active_result,
    }
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=commands)
    commands[parser.parse_args().command]()
