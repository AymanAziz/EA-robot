"""Session boundaries and reconciliation, independent of terminal process control."""

from datetime import UTC, datetime, time
from decimal import Decimal
from zoneinfo import ZoneInfo

ZONE = ZoneInfo("Asia/Kuala_Lumpur")


def session_window(now):
    if now.tzinfo is None:
        raise ValueError("Timezone-aware time required")
    local = now.astimezone(ZONE)
    start = datetime.combine(local.date(), time(0), ZONE)
    end = datetime.combine(local.date(), time(6, 30), ZONE)
    return {"date": local.date().isoformat(), "start_utc": int(start.timestamp()),
            "end_utc": int(end.timestamp()), "inside": start <= local < end,
            "start_local": start.isoformat(), "end_local": end.isoformat()}


def make_run(now, *, check=False):
    window = session_window(now)
    day = window["date"].replace("-", "")
    return {**window, "run_id": ("M05C_"+now.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ") if check else "M05D_"+day),
            "magic_base": 910_000_000_000+int(day)*100, "max_trades": 7,
            "loss_limit_usc": 10., "demo_only": True, "step7_passed": False,
            "variant": "M05_CHANNEL_SESSION_DEMO", "signal_timeframe": "M5", "bar_seconds": 300, "check_only": check}


def flatten_deadline(window, market_end_utc=0):
    deadline = window["end_utc"]
    if market_end_utc:
        deadline = min(deadline, market_end_utc-120)
    day = datetime.fromtimestamp(window["start_utc"], UTC)
    if day.weekday() == 4:
        deadline = min(deadline, int(day.replace(hour=20, minute=0, second=0).timestamp()))
    return deadline


def reconcile(history, magic_base, max_trades):
    unique = {}
    for row in history:
        key = row["deal"]
        if key in unique and unique[key] != row:
            raise ValueError("Conflicting duplicate broker deal")
        unique[key] = row
    entries = [r for r in unique.values() if r["entry"] == "0" and r["symbol"] == "XAUUSD.c"
               and magic_base < int(r["magic"]) <= magic_base+max_trades]
    if len({r["magic"] for r in entries}) != len(entries):
        raise ValueError("Repeated entry magic indicates a duplicated order attempt")
    records = []
    for entry in entries:
        position = entry["position"]
        deals = [r for r in unique.values() if r["position"] == position]
        ins = [r for r in deals if r["entry"] == "0"]
        outs = [r for r in deals if r["entry"] in ("1", "3")]
        if len(ins) != 1 or not outs:
            raise ValueError("Broker position is not fully closed")
        if Decimal(entry["volume"]) != Decimal("0.01") or any(r["symbol"] != "XAUUSD.c" for r in deals):
            raise ValueError("Unexpected entry volume or symbol")
        if sum((Decimal(r["volume"]) for r in outs), Decimal(0)) != Decimal(entry["volume"]):
            raise ValueError("Position volume remains open")
        pnl = sum((sum((Decimal(r[k]) for k in ("profit", "commission", "swap", "fee")), Decimal(0)) for r in deals), Decimal(0))
        last = max(outs, key=lambda r: int(r["time_server_epoch"]))
        held = int(last["time_server_epoch"])-int(entry["time_server_epoch"])
        if held < 0 or not pnl.is_finite():
            raise ValueError("Invalid broker timing or P&L")
        records.append({"position": position, "entry_deal": entry["deal"], "exit_deals": [r["deal"] for r in outs],
                        "entry_price": float(entry["price"]), "last_exit_price": float(last["price"]),
                        "held_seconds": held, "pnl_usc": float(pnl), "exit_reason": last["reason"]})
    return records
