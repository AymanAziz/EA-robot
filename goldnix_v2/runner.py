"""Run the single predeclared V2 experiment and unchanged Step-6 gates."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from gates.freeze import verify_freeze
from ingest.gaps import find_gaps
from ingest.ingest import load_bars
from metrics.bootstrap import monthly_block_bootstrap
from metrics.montecarlo import monte_carlo_drawdown
from metrics.report import longest_losing_streak, reference_win_rates, time_in_market_share
from params.config import dump_yaml, load_yaml
from sim.engine import prepare_bars, run_engine

from goldnix_v2.baseline import run_v2_random_baseline
from goldnix_v2.signal import apply_v2_confirmation
from goldnix_v2.step6 import evaluate_v2_gates


ROOT = Path(__file__).parents[1]
V1_ROOT = ROOT / "goldnix"
V2_ROOT = ROOT / "goldnix_v2"
DATA_PATH = V1_ROOT / "data" / "clean" / "xauusd_h1_20030505_20251231_bid_ask.csv"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _prepare_era(
    bars: pd.DataFrame,
    *,
    name: str,
    era: dict,
    config: dict,
) -> pd.DataFrame:
    timestamps = pd.DatetimeIndex(bars["timestamp_utc"])
    start = pd.Timestamp(era["start_utc"])
    end = pd.Timestamp(era["end_utc"])
    first = int(timestamps.searchsorted(start, side="left"))
    last = int(timestamps.searchsorted(end, side="right"))
    warmup = int(config["warmup_h1_bars"])
    frame = bars.iloc[max(0, first - warmup) : last].copy()
    frame["era"] = name
    prepared = prepare_bars(frame, config)
    prepared = apply_v2_confirmation(
        prepared,
        h4_period=int(config["h4_aroon_period"]),
        ties=config["ties"],
        max_spread_atr=float(config["vol_ceiling_atr"]),
        server_timezone=config["server_timezone"],
    )
    in_era = prepared["timestamp_utc"].between(start, end, inclusive="both")
    return prepared.loc[in_era].reset_index(drop=True)


def _trade_summary(trades: pd.DataFrame, baseline_mean: float) -> dict:
    longs = trades["dir"].eq("BUY")
    shorts = trades["dir"].eq("SELL")
    return {
        "baskets": len(trades),
        "longs": int(longs.sum()),
        "shorts": int(shorts.sum()),
        "win_rate": float(trades["r_multiple"].gt(0).mean()),
        "mean_r": float(trades["r_multiple"].mean()),
        "long_mean_r": float(trades.loc[longs, "r_multiple"].mean()),
        "short_mean_r": float(trades.loc[shorts, "r_multiple"].mean()),
        "baseline_mean_r": float(baseline_mean),
        "signal_minus_baseline_r": float(trades["r_multiple"].mean() - baseline_mean),
        "gap_risk_share": float(trades["flags"].eq("gap_risk").mean()),
        "spread_paid_usd": float(trades["spread_paid"].sum()),
    }


def _descriptive_report(
    trades: pd.DataFrame,
    bars: pd.DataFrame,
    config: dict,
    bootstrap,
) -> dict:
    references = reference_win_rates(
        trades,
        stop_atr=float(config["stop_atr"]),
        min_distance_usd=float(config["min_distance_usd"]),
    )
    return {
        "baskets": len(trades),
        "mean_r": float(trades["r_multiple"].mean()),
        "win_rate": float(trades["r_multiple"].gt(0).mean()),
        "bootstrap_se": bootstrap.standard_error,
        "bootstrap_lower_bound_5pct": bootstrap.lower_bound,
        "longest_losing_streak": longest_losing_streak(trades["r_multiple"]),
        "mean_mae_r": float(trades["mae_r"].mean()),
        "mean_mfe_r": float(trades["mfe_r"].mean()),
        "time_in_market_share": time_in_market_share(trades, bars),
        "spread_paid_usd": float(trades["spread_paid"].sum()),
        **references,
    }


def run() -> Path:
    """Execute V2 once and write reproducible Step-6 artifacts."""
    if not verify_freeze(V1_ROOT):
        raise RuntimeError("refusing V2 run because the frozen V1 boundary changed")

    config_path = V2_ROOT / "decision.yaml"
    config = load_yaml(config_path)
    eras_config = load_yaml(V1_ROOT / "data" / "eras.yaml")["eras"]
    bars = load_bars(DATA_PATH)
    gaps = find_gaps(bars)

    era_bars: dict[str, pd.DataFrame] = {}
    era_trades: dict[str, pd.DataFrame] = {}
    era_baselines = {}
    era_reports = {}
    fill_deltas = {}
    baseline_trade_frames = []
    baseline_draw_frames = []

    for era_number, (name, era) in enumerate(eras_config.items()):
        prepared = _prepare_era(bars, name=name, era=era, config=config)
        era_bars[name] = prepared
        result = run_engine(prepared, config, gaps=gaps)
        trades = result.trades.copy()
        era_trades[name] = trades
        longs = int(trades["dir"].eq("BUY").sum())
        shorts = int(trades["dir"].eq("SELL").sum())
        baseline = run_v2_random_baseline(
            prepared,
            config,
            longs=longs,
            shorts=shorts,
            draws=int(config["baseline_draws"]),
            seed=int(config["baseline_seed"]) + era_number * 1000,
        )
        era_baselines[name] = baseline
        baseline_trades = baseline.trades.copy()
        baseline_trades["era"] = name
        baseline_trade_frames.append(baseline_trades)
        baseline_draws = baseline.draws.copy()
        baseline_draws["era"] = name
        baseline_draw_frames.append(baseline_draws)

        target_config = {**config, "fill_policy": "target_first"}
        target_trades = run_engine(prepared, target_config, gaps=gaps).trades
        stop_win = float(trades["r_multiple"].gt(0).mean())
        target_win = float(target_trades["r_multiple"].gt(0).mean())
        fill_deltas[name] = abs(target_win - stop_win) * 100

        raw = prepared["raw_signal"].isin([-1, 1])
        direction_confirmed = (
            (prepared["raw_signal"].eq(1) & prepared["h4_oscillator"].gt(0))
            | (prepared["raw_signal"].eq(-1) & prepared["h4_oscillator"].lt(0))
        )
        baseline_mean = float(baseline.draws["mean_r"].mean())
        summary = _trade_summary(trades, baseline_mean)
        summary.update(
            {
                "raw_h1_crosses": int(raw.sum()),
                "h4_confirmed_crosses": int(direction_confirmed.sum()),
                "cost_eligible_crosses": int(prepared["signal"].isin([-1, 1]).sum()),
                "h4_reject_share": float((raw & ~direction_confirmed).sum() / raw.sum()),
                "cost_reject_share_of_h4_confirmed": float(
                    (direction_confirmed & ~prepared["cost_eligible"]).sum()
                    / direction_confirmed.sum()
                ),
                "baseline_eligible_buy_bars": baseline.eligible_bars["BUY"],
                "baseline_eligible_sell_bars": baseline.eligible_bars["SELL"],
                "fill_policy_win_rate_delta_pp": fill_deltas[name],
            }
        )
        era_reports[name] = summary

    pooled_trades = pd.concat(era_trades.values(), ignore_index=True)
    pooled_bars = pd.concat(era_bars.values(), ignore_index=True)
    baseline_trades = pd.concat(baseline_trade_frames, ignore_index=True)
    baseline_draw_means = baseline_trades.groupby("draw")["r_multiple"].mean()

    bootstrap = monthly_block_bootstrap(
        pooled_trades,
        resamples=int(config["bootstrap_resamples"]),
        seed=int(config["bootstrap_seed"]),
        baseline_draw_means=baseline_draw_means,
    )
    for era_number, name in enumerate(eras_config):
        era_bootstrap = monthly_block_bootstrap(
            era_trades[name],
            resamples=int(config["bootstrap_resamples"]),
            seed=int(config["bootstrap_seed"]) + era_number + 1,
        )
        era_reports[name]["bootstrap_se"] = era_bootstrap.standard_error
        era_reports[name]["bootstrap_lower_bound_5pct"] = era_bootstrap.lower_bound

    span_years = (
        pd.Timestamp(eras_config["D"]["end_utc"])
        - pd.Timestamp(eras_config["A"]["start_utc"])
    ).total_seconds() / (365.2425 * 24 * 3600)
    observed_trades_per_year = len(pooled_trades) / span_years
    trades_per_year = max(1, round(observed_trades_per_year))
    stop_distance = np.maximum(
        pooled_trades["atr"].to_numpy() * float(config["stop_atr"]),
        float(config["min_distance_usd"]),
    )
    observed_pnl = pooled_trades["r_multiple"].to_numpy() * stop_distance
    monte_carlo = monte_carlo_drawdown(
        observed_pnl,
        trades_per_year=trades_per_year,
        simulations=int(config["monte_carlo_paths"]),
        seed=int(config["monte_carlo_seed"]),
    )

    gap_risk_share = float(pooled_trades["flags"].eq("gap_risk").mean())
    positive_eras = sum(report["mean_r"] > 0 for report in era_reports.values())
    parity_text = (V1_ROOT / "parity" / "ATR_PARITY_RESULT.md").read_text(
        encoding="utf-8"
    )
    gate_inputs = {
        "account_usd": float(config["account_usd"]),
        "bootstrap_lower_bound": bootstrap.lower_bound,
        "signal_minus_baseline": bootstrap.edge_point_estimate,
        "edge_lower_bound": bootstrap.edge_lower_bound,
        "positive_eras": positive_eras,
        "baskets": len(pooled_trades),
        "gap_risk_share": gap_risk_share,
        "mc_p99_drawdown_usd": monte_carlo.p99_max_drawdown_usd,
        "max_fill_delta_pp": max(fill_deltas.values()),
        "atr_parity": "- Result: PASS" in parity_text,
    }
    evaluation = evaluate_v2_gates(gate_inputs)
    pooled_baseline_mean = float(baseline_draw_means.mean())
    pooled_summary = _trade_summary(pooled_trades, pooled_baseline_mean)
    pooled_report = _descriptive_report(
        pooled_trades,
        pooled_bars,
        config,
        bootstrap,
    )
    pooled_report.update(
        {
            "observed_trades_per_year": observed_trades_per_year,
            "monte_carlo_trades_per_year": trades_per_year,
            "monte_carlo_paths": monte_carlo.simulations,
            "monte_carlo_p99_max_drawdown_usd": monte_carlo.p99_max_drawdown_usd,
            "signal_minus_baseline_point": bootstrap.edge_point_estimate,
            "signal_minus_baseline_lower_bound_5pct": bootstrap.edge_lower_bound,
        }
    )

    data_hash = _sha256(V1_ROOT / "data" / "raw" / DATA_PATH.name)
    run_digest = hashlib.sha256(config_path.read_bytes() + data_hash.encode()).hexdigest()
    run_dir = V2_ROOT / "out" / f"run_{run_digest[:12]}"
    run_dir.mkdir(parents=True, exist_ok=True)
    pooled_trades.to_csv(run_dir / "trades.csv", index=False)
    pd.concat(baseline_draw_frames, ignore_index=True).to_csv(
        run_dir / "baseline_draws.csv",
        index=False,
    )
    (run_dir / "data_hash.txt").write_text(data_hash + "\n", encoding="utf-8")
    dump_yaml(config, run_dir / "config.yaml")
    metrics = {
        "strategy_version": 2,
        "run_hash": run_digest[:12],
        "data_sha256": data_hash,
        "decision_config_sha256": _sha256(config_path),
        "verdict": evaluation.verdict,
        "eras": era_reports,
        "pooled": pooled_summary,
        "step6": {
            "gate_inputs": gate_inputs,
            "gates": evaluation.gates,
            "pooled_report": pooled_report,
        },
    }
    (run_dir / "metrics.json").write_text(
        json.dumps(metrics, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (run_dir / "gates.json").write_text(
        json.dumps(
            {
                "verdict": evaluation.verdict,
                "inputs": gate_inputs,
                "gates": evaluation.gates,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    verdict_lines = [
        "# V2 Step-6 verdict",
        "",
        f"**{evaluation.verdict}**",
        "",
        "| Gate | Pass | Value | Rule |",
        "|---|---:|---:|---|",
    ]
    for gate, outcome in evaluation.gates.items():
        verdict_lines.append(
            f"| {gate} | {'YES' if outcome['passed'] else 'NO'} | "
            f"{outcome['value']} | {outcome['rule']} |"
        )
    (run_dir / "verdict.md").write_text(
        "\n".join(verdict_lines) + "\n",
        encoding="utf-8",
    )

    if not verify_freeze(V1_ROOT):
        raise RuntimeError("V1 freeze boundary changed during V2 run")
    return run_dir


if __name__ == "__main__":
    print(run())

