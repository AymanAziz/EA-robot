"""Cost accounting scenarios on fixed completed trades; these are not backtests."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from metrics.bootstrap import monthly_block_bootstrap
from metrics.montecarlo import monte_carlo_drawdown


def rebated_trades(trades: pd.DataFrame, *, fraction: float) -> pd.DataFrame:
    """Credit recorded spread to fixed exits, keeping the original ATR stop floor."""
    if not np.isfinite(fraction) or not 0 <= fraction <= 1:
        raise ValueError("rebate fraction must be within [0, 1]")
    result = trades.copy()
    distance = np.maximum(result["atr"].to_numpy(), 0.5)
    result["r_multiple"] += fraction * result["spread_paid"] / distance
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    records = []
    for name, path in [
        ("V1", Path("goldnix/out/run_f8058f65db29")),
        ("V2", Path("goldnix_v2/out/run_5f16e32256eb")),
    ]:
        trades = pd.read_csv(path / "trades.csv")
        metrics = json.loads((path / "metrics.json").read_text())
        rate = metrics["step6"]["pooled_report"]["monte_carlo_trades_per_year"]
        for rebate in (0.0, 0.5, 1.0):
            frame = rebated_trades(trades, fraction=rebate)
            bootstrap = monthly_block_bootstrap(frame, resamples=10000, seed=20261110)
            distance = np.maximum(frame.atr.to_numpy(), 0.5)
            mc = monte_carlo_drawdown(
                frame.r_multiple.to_numpy() * distance,
                trades_per_year=rate, simulations=100000, seed=20261111,
            )
            records.append({
                "study": name, "spread_rebate_fraction": rebate,
                "baskets": len(frame), "mean_r": frame.r_multiple.mean(),
                "mean_r_lower_bound": bootstrap.lower_bound,
                "positive_eras": int((frame.groupby("era").r_multiple.mean() > 0).sum()),
                "p99_1oz_usd": mc.p99_max_drawdown_usd,
                "p99_0_01oz_usd_conditional": mc.p99_max_drawdown_usd * 0.01,
                "source_trades_sha256": hashlib.sha256((path / "trades.csv").read_bytes()).hexdigest(),
            })
    result = {
        "status": "ACCOUNTING_SCENARIOS_ONLY_NO_STEP6_VERDICT",
        "assumptions": "Same trade timestamps, exits and R denominator; credited entry spread; "
        "same risk distribution at smaller exposure. Eligibility, fills, baseline, commissions, "
        "swaps, slippage and another venue's actual prices are not recomputed. "
        "G2/G3 remain unevaluated; full spread credit is not an executable cost assumption.",
        "scenarios": records,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(json.dumps(result, indent=2, allow_nan=False))
