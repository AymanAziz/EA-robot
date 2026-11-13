"""Screen actual contract economics while retaining the fixed $20 study budget."""

import argparse
import csv
import hashlib
import json
import math
from datetime import UTC, datetime
from pathlib import Path


def _number(row, key, *, positive=True):
    value = float(row[key])
    if not math.isfinite(value) or (positive and value <= 0):
        raise ValueError(f"{key} must be finite" + (" and positive" if positive else ""))
    return value


def qualify_snapshot(row, *, reference_p99_per_oz, now_epoch):
    if row.get("status") != "OK" or row.get("currency") not in {"USD", "USC"}:
        raise ValueError("Successful USD/USC account calculations required")
    if row.get("base_currency") != "XAU" or row.get("profit_currency") != "USD":
        raise ValueError("Need verified XAU with USD quote economics; other profit currencies require explicit review")
    for key, expected in {"account_trade_mode": 0, "connected": 1, "is_custom_symbol": 0,
                          "symbol_trade_mode": 4, "margin_mode": 2}.items():
        if _number(row, key, positive=False) != expected:
            raise ValueError(f"Unsupported {key}; need {expected}")
    for key in ("equity", "volume_min", "volume_step", "contract_size", "loss_buy_one_unit",
                "loss_sell_one_unit", "price_move", "margin_buy", "margin_sell", "bid", "ask"):
        _number(row, key)
    _number(row, "margin_free", positive=False)
    if float(row["ask"]) < float(row["bid"]):
        raise ValueError("Crossed quote")
    if not math.isfinite(reference_p99_per_oz) or reference_p99_per_oz <= 0:
        raise ValueError("Positive reference drawdown required")
    age = now_epoch - _number(row, "captured_utc_epoch")
    quote_age = _number(row, "quote_age_seconds", positive=False)
    if not math.isfinite(now_epoch) or not 0 <= age <= 300 or not 0 <= quote_age <= 300:
        raise ValueError("Snapshot and quote must be current within five minutes, without future timestamps")
    factor = {"USD": 1., "USC": .01}[row["currency"]]
    equity = float(row["equity"]) * factor
    free = float(row["margin_free"]) * factor
    exposure = max(float(row["loss_buy_one_unit"]), float(row["loss_sell_one_unit"])) * factor
    exposure /= float(row["price_move"])
    margin = max(float(row["margin_buy"]), float(row["margin_sell"])) * factor
    minimum_stop = _number(row, "point") * _number(row, "stops_level", positive=False)
    if minimum_stop < 0:
        raise ValueError("Negative broker stop distance")
    conditional = reference_p99_per_oz * exposure
    budget = min(20., equity)
    margin_fits = margin <= min(budget, free)
    risk_fits = conditional <= .12 * budget
    return {
        "symbol": row["symbol"], "server": row["server"], "equity_usd": equity,
        "study_budget_usd": budget, "exposure_usd_per_price_unit": exposure,
        "minimum_margin_usd": margin, "conditional_p99_usd": conditional,
        "drawdown_limit_usd": .12 * budget, "margin_fits": margin_fits,
        "conditional_g7_fits": risk_fits, "broker_min_stop_price": minimum_stop,
        "contract_screen_pass": margin_fits and risk_fits and minimum_stop <= .5,
        "step6_approved": False,
        "limitation": "Contract screen only. Historical venue costs and independent strategy evidence remain unverified.",
    }


def qualify_file(path, *, reference_p99_per_oz, now_epoch):
    symbols, rejected = [], []
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            try:
                symbols.append(qualify_snapshot(row, reference_p99_per_oz=reference_p99_per_oz,
                                                now_epoch=now_epoch))
            except (ValueError, KeyError, TypeError) as error:
                rejected.append({"symbol": row.get("symbol"), "reason": str(error)})
    return {"symbols": symbols, "rejected": rejected, "step6_approved": False,
            "evaluated_utc_epoch": now_epoch, "fixed_study_budget_usd": 20.}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    from goldnix_step7.runner import preflight
    preflight(root)
    for folder in ("goldnix_research", "goldnix_round2", "goldnix_round3"):
        files = json.loads((root / folder / "out/MANIFEST.json").read_text())["file_sha256"]
        for name, expected in files.items():
            if hashlib.sha256((root / name).read_bytes()).hexdigest() != expected:
                raise PermissionError(f"Previous evidence changed: {name}")
    reference_path = root / "goldnix_round2/out/S11/metrics.json"
    reference = json.loads(reference_path.read_text())
    now = datetime.now(UTC)
    result = qualify_file(args.snapshot, reference_p99_per_oz=reference["p99_usd_at_verified_1oz"],
                           now_epoch=now.timestamp())
    result.update({"reference_candidate": "S11", "reference_mean_r": reference["bootstrap"]["mean_r"],
                   "reference_sha256": hashlib.sha256(reference_path.read_bytes()).hexdigest(),
                   "snapshot_sha256": hashlib.sha256(args.snapshot.read_bytes()).hexdigest(),
                   "evaluated_utc": now.isoformat(), "orders_sent": False})
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / "snapshot.csv").write_bytes(args.snapshot.read_bytes())
    manifest = {}
    directory = Path(__file__).resolve().parent
    for path in directory.rglob("*"):
        if not path.is_file() or path.suffix not in {".py", ".mq5", ".ini"} or "out" in path.relative_to(directory).parts:
            continue
        name = path.relative_to(directory)
        target = args.output / "source" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(path.read_bytes())
        manifest[name.as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    result["source_sha256"] = manifest
    (args.output / "QUALIFICATION.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"symbols": result["symbols"], "rejected": result["rejected"],
                      "step6_approved": False, "output": str(args.output)}, indent=2), flush=True)


if __name__ == "__main__":
    main()
