"""Bounded read-only broker history probe for the Step 8 continuation."""

import csv
import json
import shutil
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path

from goldnix_venue.demo_session import Terminal

HERE = Path(__file__).resolve().parent


def main():
    terminal = Terminal()
    login = terminal.login()
    terminal.check_charts()
    run_id = datetime.now(UTC).strftime("S8P_%Y%m%dT%H%M%SZ")
    output = HERE / "out" / run_id
    output.mkdir(parents=True, exist_ok=False)
    source = HERE / "ProbeH01History.mq5"
    shutil.copy2(source, terminal.build / source.name)
    log = terminal.build / f"{run_id}_compile.log"
    subprocess.run([str(terminal.wine), str(terminal.root / "metaeditor64.exe"),
        f"/compile:C:\\Goldnix\\{source.name}", f"/log:C:\\Goldnix\\{log.name}"],
        env=terminal.env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60)
    compilation = log.read_text(encoding="utf-16")
    (output / "compile.log").write_text(compilation)
    if "0 errors, 0 warnings" not in compilation:
        raise RuntimeError(f"Compile error: {output}")
    for suffix in ("mq5", "ex5"):
        file = terminal.build / f"ProbeH01History.{suffix}"
        shutil.copy2(file, terminal.root / "MQL5/Scripts/Goldnix" / file.name)
        shutil.copy2(file, output / file.name)
    preset = f"{run_id}.set"
    terminal.preset(preset, {"ExpectedLogin": login, "RunId": run_id})
    config = terminal.config({"run_id": run_id}, "ProbeH01History", preset, False)
    (output / "STARTED.json").write_text(json.dumps({"run_id": run_id,
        "created_utc": datetime.now(UTC).isoformat(), "read_only": True,
        "h1_server_window": ["2024-01-22", "2024-03-01"], "tick_probe_server_day": "2024-02-15",
        "clock_validation_registered_before_comparison": {"offsets_hours": [0, 1, 2, 3, 4],
          "return_correlation_min": .90, "correlation_margin_min": .30,
          "median_absolute_bid_close_difference_max": 2.0, "weekly_minimum_pairs": 50}}, indent=2)+"\n")
    try:
        terminal.restart(config, output, disable=True)
        marker = terminal.common / f"H01_{run_id}_meta.csv"
        for _ in range(240):
            if marker.exists():
                with marker.open() as stream:
                    receipt = dict(csv.reader(stream))
                if receipt.get("completed") == "1":
                    for kind in ("h1.csv", "ticks.bin", "meta.csv"):
                        shutil.copy2(terminal.common / f"H01_{run_id}_{kind}", output / kind)
                    (HERE / "PROBE_LATEST.json").write_text(json.dumps({"output": str(output)}, indent=2)+"\n")
                    print(json.dumps({"output": str(output), "receipt": receipt}, indent=2), flush=True)
                    return
            time.sleep(1)
        raise RuntimeError(f"Probe timed out; inspect {output}")
    finally:
        (terminal.root / "MQL5/Presets" / preset).unlink(missing_ok=True)


if __name__ == "__main__":
    main()
