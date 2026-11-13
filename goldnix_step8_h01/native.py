"""Compile and launch one native MT5 Strategy Tester run with live trading disabled."""

import argparse
import hashlib
import json
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from goldnix_venue.demo_session import Terminal

HERE = Path(__file__).resolve().parent


def launch(config_path=None):
    config_path = Path(config_path) if config_path else HERE / "decision.json"
    config = json.loads(config_path.read_text())
    frozen = json.loads((HERE / "out/S8_20261112T152435Z/decision.json").read_text())
    if config["inputs"] != frozen["inputs"]:
        raise ValueError("H01 strategy parameters changed; this runner only validates the frozen strategy")
    run_id = datetime.now(UTC).strftime("S8_%Y%m%dT%H%M%SZ")
    output = HERE / "out" / run_id
    output.mkdir(parents=True, exist_ok=False)
    if config.get("clock_evidence"):
        evidence = HERE.parent / config["clock_evidence"]
        if hashlib.sha256(evidence.read_bytes()).hexdigest() != config["clock_evidence_sha256"]:
            raise ValueError("Clock evidence changed")
        clock = json.loads(evidence.read_text())
        if not clock["passed"] or clock["selected_offset_seconds"] != config["operational_inputs"]["ServerOffsetSeconds"]:
            raise ValueError("Clock evidence does not support configured offset")
        shutil.copy2(evidence, output / "CLOCK_CHECK.json")
    terminal = Terminal()
    terminal.login()  # Check saved broker identity without exposing it.
    terminal.check_charts()
    source = HERE / "H01Channel.mq5"
    shutil.copy2(source, terminal.build / source.name)
    compile_log = terminal.build / f"{run_id}_compile.log"
    subprocess.run([str(terminal.wine), str(terminal.root / "metaeditor64.exe"),
                    "/compile:C:\\Goldnix\\H01Channel.mq5", f"/log:C:\\Goldnix\\{compile_log.name}"],
                   env=terminal.env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60)
    compilation = compile_log.read_text(encoding="utf-16")
    (output / "compile.log").write_text(compilation)
    if "0 errors, 0 warnings" not in compilation:
        raise RuntimeError(f"Native compilation failed: {output / 'compile.log'}")
    install = terminal.root / "MQL5/Experts/GoldnixH01"
    install.mkdir(parents=True, exist_ok=True)
    hashes = {}
    for suffix in ("mq5", "ex5"):
        artifact = terminal.build / f"H01Channel.{suffix}"
        shutil.copy2(artifact, install / artifact.name)
        shutil.copy2(artifact, output / artifact.name)
        hashes[artifact.name] = hashlib.sha256(artifact.read_bytes()).hexdigest()
    values = {**config["inputs"], **config["operational_inputs"], "RunId": run_id}
    parameters = "".join(f"{k}={v}\n" for k, v in values.items())
    preset = terminal.root / "MQL5/Profiles/Tester" / f"{run_id}.set"
    preset.parent.mkdir(parents=True, exist_ok=True)
    preset.write_text(parameters)
    (output / "inputs.set").write_text(parameters)
    (terminal.root / "reports/GoldnixH01").mkdir(parents=True, exist_ok=True)
    tester = config.get("tester", {"model": 4, "from_date": "2026.11.02", "to_date": "2026.11.12"})
    ini = ("[Experts]\nEnabled=0\nAllowLiveTrading=0\nAllowDllImport=0\nAccount=1\nProfile=1\n"
           "\n[Tester]\nExpert=GoldnixH01\\H01Channel.ex5\n"
           f"ExpertParameters={preset.name}\nSymbol=XAUUSD.c\nPeriod=H1\n"
           f"Model={tester['model']}\nExecutionMode=0\nOptimization=0\nFromDate={tester['from_date']}\nToDate={tester['to_date']}\n"
           "ForwardMode=0\nDeposit=20\nCurrency=USD\nLeverage=1:100\n"
           "UseLocal=1\nUseRemote=0\nUseCloud=0\nVisual=0\n"
           f"Report=reports\\GoldnixH01\\{run_id}_report.htm\nReplaceReport=0\nShutdownTerminal=1\n")
    launch_file = terminal.build / f"{run_id}_tester.ini"
    launch_file.write_text(ini)
    (output / "tester.ini").write_text(ini)
    (output / "decision.json").write_bytes(config_path.read_bytes())
    (output / "SOURCE").mkdir()
    for path in HERE.iterdir():
        if path.is_file() and path.suffix in (".py", ".mq5"):
            shutil.copy2(path, output / "SOURCE" / path.name)
            hashes[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    started = {"run_id": run_id, "started_utc": datetime.now(UTC).isoformat(),
               "source_sha256": hashes, "strategy": config["candidate_id"],
               "step7_passed": False, "tester_only": True,
               "original_result_sha256": hashlib.sha256((HERE.parent /
                   "goldnix_mtf2/out/H01_S11_M5_REPLAY/RESULT.json").read_bytes()).hexdigest()}
    (output / "STARTED.json").write_text(json.dumps(started, indent=2)+"\n")
    terminal.restart(launch_file, output, disable=True)
    (HERE / "LATEST.json").write_text(json.dumps({"output": str(output)}, indent=2)+"\n")
    print(json.dumps({"started": True, "output": str(output), "run_id": run_id}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path)
    launch(parser.parse_args().config)
