"""Recorded follow-up: causal nominal-risk eligibility at a documented product exposure."""

import hashlib
import json
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from goldnix_research.candidates import prepare_candidate
from goldnix_research.screen import candidate_eras, screen_candidate
from goldnix_step7.runner import preflight
from metrics.montecarlo import monte_carlo_drawdown
from params.config import load_yaml


def apply_risk_budget(frame, *, stop_atr, account_usd, risk_share, usd_per_price_unit):
    """Filter by signal-close nominal stop loss; gaps and next-open spread can exceed it."""
    values = [stop_atr, account_usd, risk_share, usd_per_price_unit]
    if not np.isfinite(values).all() or not all(v > 0 for v in values):
        raise ValueError("Risk inputs must be positive and finite")
    result = frame.copy()
    spread = result.ask_close - result.bid_close
    distance = np.maximum(result.atr * stop_atr, .5)
    nominal = (distance + spread) * usd_per_price_unit
    eligible = np.isfinite(nominal) & spread.ge(0) & nominal.le(account_usd * risk_share)
    result["nominal_stop_loss_usd"] = nominal
    result["risk_eligible"] = eligible
    result["signal"] = result.signal.where(eligible, 0)
    result["buy_eligible"] &= eligible
    result["sell_eligible"] &= eligible
    return result


def prepare_risk_candidate(bars, candidate):
    return apply_risk_budget(prepare_candidate(bars, candidate), stop_atr=candidate["stop_atr"],
                             account_usd=candidate["account_usd"], risk_share=candidate["risk_share"],
                             usd_per_price_unit=candidate["usd_per_price_unit"])


def _worker(root, candidate, protocol):
    root = Path(root)
    eras = candidate_eras(root, candidate, protocol)
    result, trades = screen_candidate(eras, candidate, load_yaml(root / "goldnix/params/decision.yaml"),
                                      protocol, prepare=prepare_risk_candidate)
    years = (pd.Timestamp("2026-01-01T00:00Z") - pd.Timestamp("2005-06-01T00:00Z")).total_seconds() / (365.2425 * 86400)
    distance = np.maximum(trades.atr.to_numpy() * candidate["stop_atr"], .5)
    risk = monte_carlo_drawdown(trades.r_multiple.to_numpy() * distance,
                               trades_per_year=max(1, round(len(trades) / years)),
                               simulations=protocol["monte_carlo_paths"], seed=protocol["monte_carlo_seed"])
    result["p99_usd_at_actual_1oz"] = risk.p99_max_drawdown_usd
    result["p99_usd_at_documented_0_01oz_scenario"] = risk.p99_max_drawdown_usd * .01
    result["conditional_G7"] = risk.p99_max_drawdown_usd * .01 <= 2.4
    result["account_verified"] = False
    result["monte_carlo_paths"] = risk.simulations
    return result, trades


def main():
    root = Path(__file__).resolve().parents[1]
    preflight(root)
    directory = root / "goldnix_research"
    original = json.loads((directory / "protocol.json").read_text())
    followup = json.loads((directory / "risk_protocol.json").read_text())
    protocol = {**original, "trial_count": followup["cumulative_trial_count"]}
    output = directory / "out/risk_screen"
    output.mkdir(parents=True, exist_ok=False)
    (output / "source").mkdir()
    manifest = {}
    for name in ("risk_budget.py", "screen.py", "candidates.py", "protocol.json", "risk_protocol.json"):
        payload = (directory / name).read_bytes()
        (output / "source" / name).write_bytes(payload)
        manifest[name] = hashlib.sha256(payload).hexdigest()
    data = root / protocol["data_path"]
    if hashlib.sha256(data.read_bytes()).hexdigest() != protocol["data_sha256"]:
        raise PermissionError("Historical data hash mismatch")
    results = []
    with ProcessPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(_worker, str(root), c, protocol) for c in followup["candidate_configs"]]
        for future in as_completed(futures):
            result, trades = future.result()
            run = output / result["id"]
            run.mkdir()
            trades.to_csv(run / "trades.csv", index=False)
            (run / "metrics.json").write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n")
            results.append(result)
            print(json.dumps({"id": result["id"], "baskets": result["baskets"],
                              "mean_r": result["bootstrap"]["mean_r"],
                              "mean_lower": result["bootstrap"]["mean_lower"],
                              "positive_eras": result["positive_eras"],
                              "conditional_p99_usd": result["p99_usd_at_documented_0_01oz_scenario"],
                              "screen_qualifies": result["eligible_for_full_evaluation"]}), flush=True)
    for name, digest in manifest.items():
        if hashlib.sha256((directory / name).read_bytes()).hexdigest() != digest:
            raise PermissionError("Follow-up source changed during execution")
    preflight(root)
    results.sort(key=lambda r: r["id"])
    qualified = [r for r in results if r["eligible_for_full_evaluation"]]
    selected = max(qualified, key=lambda r: (r["bootstrap"]["selection_lower"], r["id"])) if qualified else None
    summary = {"status": "SCREEN_COMPLETE", "approval": "EXPLORATORY_ONLY", "account_verified": False,
               "completed_utc": datetime.now(UTC).isoformat(), "source_sha256": manifest,
               "additional_trials": len(results), "cumulative_trials": protocol["trial_count"],
               "qualified": [r["id"] for r in qualified], "selected": selected["id"] if selected else None,
               "results": results}
    (output / "SUMMARY.json").write_text(json.dumps(summary, indent=2, sort_keys=True, allow_nan=False) + "\n")
    print(json.dumps({"qualified": summary["qualified"], "selected": summary["selected"]}), flush=True)


if __name__ == "__main__":
    main()
