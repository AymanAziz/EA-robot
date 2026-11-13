"""Post-screen accounting diagnostics; never substitute them for executable trades."""

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from goldnix_research.screen import screen_statistics
from goldnix_step7.runner import preflight
from metrics.montecarlo import monte_carlo_drawdown


def credit_spread(trades, *, stop_atr, fraction):
    """Credit a hypothetical fraction of spread at the original stop-distance denominator."""
    if not np.isfinite(stop_atr) or stop_atr <= 0 or not np.isfinite(fraction) or not 0 <= fraction <= 1:
        raise ValueError("Positive stop multiple and a credit fraction in [0,1] required")
    adjusted = trades.copy()
    distance = np.maximum(adjusted.atr.to_numpy() * stop_atr, .5)
    adjusted["r_multiple"] += fraction * adjusted.spread_paid / distance
    return adjusted


def main():
    root = Path(__file__).resolve().parents[1]
    preflight(root)
    directory = root / "goldnix_research"
    protocol = json.loads((directory / "protocol.json").read_text())
    screen = json.loads((directory / "out/screen/SUMMARY.json").read_text())
    # This post-screen diagnostic concerns the two channel leads; neither is promoted.
    records = []
    for candidate_id in ("C20", "C24"):
        candidate = next(r for r in screen["results"] if r["id"] == candidate_id)["candidate"]
        path = directory / "out/screen" / candidate_id / "trades.csv"
        trades = pd.read_csv(path)
        start, end = pd.Timestamp("2005-06-01T00:00Z"), pd.Timestamp("2025-12-31T23:00Z")
        years = ((end - start).total_seconds() + 3600) / (365.2425 * 86400)
        rate = max(1, round(len(trades) / years))
        distance = np.maximum(trades.atr.to_numpy() * candidate["stop_atr"], .5)
        risk = monte_carlo_drawdown(trades.r_multiple.to_numpy() * distance,
                                   trades_per_year=rate, simulations=protocol["monte_carlo_paths"],
                                   seed=protocol["monte_carlo_seed"])
        costs = []
        for credit in (0., .25, .5, .75, 1.):
            adjusted = credit_spread(trades, stop_atr=candidate["stop_atr"], fraction=credit)
            stats = screen_statistics(adjusted, start=start, end=end, trials=protocol["trial_count"],
                                      resamples=protocol["bootstrap_resamples"], seed=protocol["bootstrap_seed"])
            costs.append({"hypothetical_spread_credit_fraction": credit, **stats})
        records.append({
            "id": candidate_id, "candidate": candidate, "baskets": len(trades),
            "source_trades_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "annual_trades": rate, "monte_carlo_paths": risk.simulations,
            "p99_usd_at_actual_1oz": risk.p99_max_drawdown_usd,
            "p99_usd_at_hypothetical_0_01oz": risk.p99_max_drawdown_usd * .01,
            "drawdown_limit_usd": 2.4, "cost_scenarios": costs,
        })
    result = {
        "status": "ACCOUNTING_DIAGNOSTIC_ONLY", "approval": False,
        "post_screen_selection": "C20 and C24 were chosen after the screen for diagnostics; neither cleared G1",
        "limitations": "Hypothetical spread credits keep original trades and fills; no revised baseline, "
        "commissions, financing, slippage, or target-venue history. The 0.01 oz scenario uses public product "
        "specifications, not an account export. Neither scenario can receive a Step 6 approval.",
        "scenarios": records,
    }
    with (directory / "out/COST_DIAGNOSTICS.json").open("x") as handle:
        json.dump(result, handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write("\n")
    for record in records:
        print(json.dumps(record), flush=True)


if __name__ == "__main__":
    main()
