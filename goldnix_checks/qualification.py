"""Screen broker snapshots; never infer strategy approval from contract size."""

from __future__ import annotations

import math
import csv
import argparse
import json
from pathlib import Path


def qualify_snapshot(row: dict, *, reference_p99_per_oz: float) -> dict:
    """Compare minimum exposure with a conditional historical dollar risk budget."""
    if row.get("status") != "OK" or row.get("currency") not in {"USD", "USC"}:
        raise ValueError("A successful USD/USC broker calculation is required")
    if row.get("base_currency") != "XAU":
        raise ValueError("Only confirmed XAU gold contracts can use this risk reference")
    for field in ("equity", "volume_min", "volume_step", "contract_size",
                  "loss_one_price_unit", "margin_buy", "margin_sell", "bid", "ask"):
        value = float(row[field])
        if not math.isfinite(value) or value <= 0:
            raise ValueError(f"{field} must be positive and finite")
    if not math.isfinite(float(row["margin_free"])):
        raise ValueError("margin_free must be finite")
    if float(row["ask"]) < float(row["bid"]):
        raise ValueError("ask must be at least bid")
    if not math.isfinite(reference_p99_per_oz) or reference_p99_per_oz <= 0:
        raise ValueError("reference drawdown must be positive and finite")
    unit_usd = {"USD": 1.0, "USC": 0.01}[row["currency"]]
    equity = float(row["equity"]) * unit_usd
    loss = float(row["loss_one_price_unit"]) * unit_usd
    margin = max(float(row["margin_buy"]), float(row["margin_sell"])) * unit_usd
    projected_p99 = reference_p99_per_oz * loss
    return {
        "symbol": row["symbol"],
        "equity_usd": equity,
        "minimum_move_loss_usd": loss,
        "minimum_margin_usd": margin,
        "quoted_spread": float(row["ask"]) - float(row["bid"]),
        "drawdown_limit_usd": equity * 0.12,
        "conditional_p99_usd": projected_p99,
        "margin_fits": margin <= float(row["margin_free"]) * unit_usd,
        "conditional_g7_fits": projected_p99 <= equity * 0.12,
        "step6_approved": False,
        "limitation": "Linear exposure scenario using the old trade distribution; "
        "not a new venue backtest or a Step-6 approval.",
    }


def qualify_file(path: str | Path, *, reference_p99_per_oz: float) -> dict:
    """Read the exporter CSV and keep unsupported calculations explicitly unqualified."""
    symbols, rejected = [], []
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            try:
                result = qualify_snapshot(row, reference_p99_per_oz=reference_p99_per_oz)
            except (ValueError, KeyError, TypeError) as error:
                rejected.append({"symbol": row.get("symbol"), "reason": str(error)})
            else:
                symbols.append(result)
    return {"symbols": symbols, "rejected": rejected, "step6_approved": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("--metrics", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    metrics = json.loads(args.metrics.read_text())
    reference = metrics["step6"]["gate_inputs"]["mc_p99_drawdown_usd"]
    report = qualify_file(args.snapshot, reference_p99_per_oz=reference)
    report["reference_metrics"] = str(args.metrics)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print(json.dumps(report, indent=2, allow_nan=False))
