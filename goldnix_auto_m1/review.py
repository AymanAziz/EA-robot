"""Read native M1 records for the user's current observation window."""
import csv
from datetime import UTC, datetime
import json
from pathlib import Path
import time
from collections import Counter

from goldnix_venue.demo_session import Terminal, write_json
from .ops import DEPLOY, status


def rows(path):
    if not path.exists() or path.stat().st_size == 0:
        return []
    with path.open() as file:
        records = list(csv.DictReader(file))
    if any(None in row or any(v is None for v in row.values()) for row in records):
        raise ValueError(f"Incomplete native row; retry after the next heartbeat: {path.name}")
    return records


def review():
    window = json.loads((DEPLOY / "ONE_HOUR_REVIEW.json").read_text())
    start = int(window["start_utc_epoch"])
    now = int(time.time())
    root = Terminal().root / "MQL5/Files/GoldnixAutoM5Demo"
    entries, exits, signals, interruptions = [], [], [], []
    for folder in sorted((root / "runs").glob("M1_AUTO_*")):
        entries += [dict(r, run=folder.name) for r in rows(folder / "entries.csv") if start <= int(r["entry_utc"]) <= now]
        exits += rows(folder / "trades.csv")
        signals += [r for r in rows(folder / "signals.csv") if start <= int(r["decision_utc"]) <= now]
        interruptions += [r for r in rows(folder / "events.csv") if start <= int(r["utc_epoch"]) <= now and r["event"] in ("PAUSE", "DEINIT")]
    magics = {r["magic"] for r in entries}
    if len(magics) != len(entries):
        raise ValueError("Duplicate entry identity; reconcile broker records before reporting totals")
    exits = [r for r in exits if r.get("magic") in magics]
    if len({r["magic"] for r in exits}) != len(exits):
        raise ValueError("Duplicate exit identity; reconcile before reporting totals")
    checks = {r["magic"] for r in entries if r["context"] == "requested_execution_check"}
    latest = status()
    own_open = latest.get("pending_magic") in magics and int(latest.get("own_positions", 0)) > 0
    result = {
        "as_of_utc": datetime.now(UTC).isoformat(), "window": window,
        "elapsed_minutes": round((now-start)/60, 2),
        "heartbeat_age_seconds": now-int(latest.get("captured_utc", 0)),
        "confirmed_entries": entries, "closed_trades": exits,
        "execution_check_entries": len(checks), "strategy_entries": len(entries)-len(checks),
        "realized_pnl_usc": round(sum(float(r["pnl_usc"]) for r in exits), 2),
        "execution_check_realized_pnl_usc": round(sum(float(r["pnl_usc"]) for r in exits if r["magic"] in checks), 2),
        "strategy_realized_pnl_usc": round(sum(float(r["pnl_usc"]) for r in exits if r["magic"] not in checks), 2),
        "signal_reasons": dict(Counter(r["reason"] for r in signals)),
        "interruptions": interruptions, "observed_position_open": own_open,
        "status": latest,
    }
    write_json(DEPLOY / "LATEST_ONE_HOUR_REVIEW.json", result)
    return result


if __name__ == "__main__":
    print(json.dumps(review(), indent=2))
