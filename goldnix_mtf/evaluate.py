"""One frozen exploratory Step 6 evaluation; never connects to MT5 or places orders."""

import json
import platform
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from gates.verdict import evaluate_gates
from goldnix_mtf.data import CACHE, ROOT, digest
from goldnix_mtf.method import features, outcome_pool, select_schedule, signals
from goldnix_step6.baseline import sample_schedules, schedule_is_valid
from goldnix_step6.bootstrap import paired_month_bootstrap
from goldnix_step6.freeze import source_manifest, verify_run
from metrics.montecarlo import max_drawdown, monte_carlo_drawdown
from params.config import load_yaml

DIRECTORY = ROOT / "goldnix_mtf"


def write_json(path, value):
    with Path(path).open("x") as handle:
        json.dump(value, handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write("\n")


def sources():
    manifest = source_manifest(ROOT)
    paths = list(DIRECTORY.glob("*.py")) + list(DIRECTORY.glob("*.json"))
    paths += list((DIRECTORY / "tests").glob("*.py"))
    paths += [ROOT / "goldnix_venue" / name for name in
              ("DemoRoundTrip.mq5", "DemoSession.mq5", "VerifyDemoBatch.mq5", "demo_session.py")]
    return {**manifest, **{p.relative_to(ROOT).as_posix(): digest(p) for p in paths}}


def preserved_freezes():
    for name in ("V1_4b823fa2ca89", "V2_f8bd017f3802"):
        if not verify_run(ROOT, ROOT / "goldnix_step6/out" / name):
            raise PermissionError(f"Existing {name} freeze is not intact")


def statistics(trades):
    if trades.empty:
        return {"trades": 0, "mean_r": None, "win_rate": None, "pnl_usd": 0.,
                "buy_trades": 0, "sell_trades": 0, "profit_factor": None, "max_drawdown_usd": 0.}
    winners = trades.r_multiple.clip(lower=0).sum()
    losers = -trades.r_multiple.clip(upper=0).sum()
    return {"trades": len(trades), "mean_r": float(trades.r_multiple.mean()),
            "win_rate": float(trades.r_multiple.gt(0).mean()), "pnl_usd": float(trades.pnl_usd.sum()),
            "buy_trades": int(trades.dir.eq("BUY").sum()), "sell_trades": int(trades.dir.eq("SELL").sum()),
            "profit_factor": float(winners / losers) if losers else None,
            "max_drawdown_usd": max_drawdown(trades.pnl_usd),
            "mean_entry_spread": float(trades.spread_paid.mean()),
            "stop_exits": int(trades.exit_reason.eq("stop").sum()),
            "gap_risk_share": float(trades["flags"].eq("gap_risk").mean())}


def sampler_statistics(diagnostics, pool, trades, protocol):
    counts = trades.dir.value_counts()
    expected = sum(counts[d] ** 2 / pool.dir.eq(d).sum() for d in counts.index) / len(trades)
    difference = diagnostics.final_mean_r - diagnostics.midpoint_mean_r
    se = float(difference.std(ddof=1) / np.sqrt(len(difference)))
    excess = float(diagnostics.initial_retention.mean() - expected)
    return {"eligible_pool_outcomes": len(pool), "mean_acceptance": float(diagnostics.acceptance_rate.mean()),
            "mean_initial_retention": float(diagnostics.initial_retention.mean()),
            "unconstrained_expected_retention": float(expected),
            "retention_excess_vs_unconstrained": excess,
            "midpoint_to_final_difference": float(difference.mean()), "difference_se": se,
            "mixing_warning": bool(excess > protocol["sampler_retention_excess_warning"]
                or abs(difference.mean()) > protocol["sampler_midpoint_difference_se_warning"] * se + 1e-12),
            "limitation": "Finite independent MCMC chains approximate uniform feasible schedules; diagnostics cannot prove convergence"}


def selection_bound(trades, protocol):
    """Additional search disclosure; unchanged raw G1 remains the declared gate."""
    months = pd.period_range("2005-06", "2025-12", freq="M").astype(str)
    labels = pd.to_datetime(trades.exit_ts, utc=True).dt.strftime("%Y-%m")
    monthly = trades.groupby(labels).r_multiple.agg(["sum", "count"]).reindex(months, fill_value=0)
    sums, counts = monthly["sum"].to_numpy(), monthly["count"].to_numpy()
    rng = np.random.default_rng(protocol["bootstrap_seed"])
    means = []
    for _ in range(protocol["bootstrap_resamples"]):
        selected = rng.integers(len(months), size=len(months))
        if counts[selected].sum():
            means.append(sums[selected].sum() / counts[selected].sum())
    alpha = .05 / protocol["cumulative_registered_variants"]
    return {"registered_trials": protocol["cumulative_registered_variants"], "alpha": alpha,
            "mean_lower": float(np.quantile(means, alpha)),
            "limitation": "Diagnostic only: 69 is the explicit registry, not every earlier design choice; only about seven bootstrap replicates lie in this extreme tail"}


def report_markdown(result):
    pooled = result["pooled"]
    lines = ["# Step 6: user's H1 → M15 → M5 method", "",
             f"Candidate **{result['candidate_id']}**, frozen before historical performance was inspected.", "",
             f"**{result['status']}**. Trading approval remains **false**. "
             "G9 is not verified for this new M5 implementation.", "",
             "This report supersedes the preserved first attempt: a midnight stop-day accounting defect "
             "was corrected without changing the registered strategy parameters or statistical seeds. "
             "Stop exit timestamps identify their M5 candle, not an observed execution second. "
             "See source/goldnix_mtf/CORRECTION.json for the audit trail.", "",
             "This is one operational interpretation of the user's idea, with declared numerical assumptions. "
             "It is not the only possible form of the method, and a failure does not reject all multi-timeframe trading.", "",
             "## Method checked", "",
             "H1 close and rising/falling EMA50 define BUY/SELL direction. A completed M15 pullback to EMA20 "
             "defines its high/low as the level. The next M5 candle must close beyond that level by a fixed buffer; "
             "the following M5 candle must retest the level band and reclaim it without excessive extension. "
             "Enter on the next available boundary quote only if confirmation still holds. No confirmed setup means SKIP.", "",
             "BUY enters ask and exits bid; SELL enters bid and exits ask. Stop is 1 gold-price-unit from the "
             "exit-side entry quote; close after five minutes if not stopped. One position, original Step6 -2R UTC "
             "daily halt, Friday/holiday exclusions and a conservative slot lockout apply equally to random entries. "
             "This historical clock is not an exact replay of the separate demo scheduler.", "",
             "## Historical result", "",
             "| Era | Trades | BUY | SELL | Win rate | Mean R | P/L at 0.01oz (USD) |",
             "|---|---:|---:|---:|---:|---:|---:|"]
    for name, stats in [*result["eras"].items(), ("All", pooled)]:
        mean = f"{stats['mean_r']:.4f}" if stats["mean_r"] is not None else "n/a"
        win = f"{stats['win_rate']:.1%}" if stats["win_rate"] is not None else "n/a"
        lines.append(f"| {name} | {stats['trades']:,} | {stats['buy_trades']:,} | {stats['sell_trades']:,} | "
                     f"{win} | {mean} | {stats['pnl_usd']:.4f} |")
    lines += ["", "R is the nominal 1-unit stop, before spread. A stopped trade can lose more than 1R. "
              "Spread is already included; do not subtract it again. Monetary values use the currently verified "
              "Cent demo exposure of 0.01oz, not a claim that these historical quotes were offered by JustMarkets.", "",
              "## Step 6 gates", "", "| Gate | Outcome | Value | Requirement |",
              "|---|---|---:|---|"]
    for gate, record in result["gates"].items():
        value = record["value"]
        rendered = f"{value:.6f}" if isinstance(value, float) else str(value)
        status = record.get("status", "PASS" if record["passed"] else "FAIL")
        lines.append(f"| {gate} | {status} | {rendered} | {record['rule']} |")
    if result.get("bootstrap"):
        boot = result["bootstrap"]
        lines += ["", f"Matched random-entry mean: **{boot['baseline_mean']:.4f}R**. "
                  f"Method minus random: **{boot['edge_point']:.4f}R**; one-sided 95% lower bound "
                  f"**{boot['edge_lower']:.4f}R**. Each era uses 200 feasible schedules matched on BUY/SELL count "
                  "and execution constraints; 10,000 paired calendar-month resamples include inactive months."]
    lines += ["", "G7 uses 100,000 IID one-year paths at the observed trade rate and USD20 account. It does "
              "not model margin, ruin, intratrade equity or unseen tail events. G8 is 0pp by construction because "
              "there is no take profit; it does not establish tick-level fills. G9 requires new M5 broker parity "
              "evidence, including higher-timeframe availability checks. The existing H1 certificate is not reused.", "",
              "## What this does and does not establish", "",
              "The confirmation rejection counts describe this filter's behavior, not a measured reduction in "
              "false-breakout losses versus an unfiltered strategy. That would require a separately registered "
              "matched comparison. Both BUY and SELL are implemented and separately reported in RESULT.json.", "",
              "History spans the original four calendar eras in 2005–2025. Only complete UTC M15/H1 aggregates "
              "are used. Missing M5 quotes are not interpolated; a missing timed-exit quote delays exit and is "
              "flagged. Intrabar stop slippage is unknowable from OHLC. Spread is modeled; commissions, financing "
              "and execution slippage are not established. Fixed extra-cost diagnostics hold the schedule fixed, "
              "so they do not resimulate daily halts. EMA buffers and other parameters were not optimized.", "",
              "This is registered candidate 69 on previously examined history. The extra selection bound is "
              "a disclosure, not a cure for repeated research. 2026 was not accessed and is not represented as an "
              "untouched holdout. The existing demo code and frozen V1/V2 evaluations were preserved.", "",
              "Data attribution: [EVTradingLabs public catalogue](https://evtradelabs.com/data), which attributes "
              "underlying ticks to Dukascopy. See DATA_MANIFEST.json for every annual archive hash.", "",
              "Review: [full metrics](RESULT.json), [executed simulated trades](trades.csv), "
              "[setup decisions](setup_decisions.csv.gz), [frozen rules](source/goldnix_mtf/protocol.json), "
              "and [source/artifact hashes](FROZEN.json).", ""]
    return "\n".join(lines)


def main():
    protocol = json.loads((DIRECTORY / "protocol.json").read_text())
    registration = json.loads((DIRECTORY / "REGISTERED.json").read_text())
    if digest(DIRECTORY / "protocol.json") != registration["protocol_sha256"] or protocol["holdout_access"]:
        raise PermissionError("Registered protocol changed or requests holdout")
    preserved_freezes()
    manifest = sources()
    data_manifest = json.loads((CACHE / "MANIFEST.json").read_text())
    if digest(CACHE / "validated.pkl") != data_manifest["validated_sha256"]:
        raise PermissionError("Validated input changed")
    for record in data_manifest["files"]:
        if digest(CACHE / f"XAUUSD_M5_{record['year']}.json.gz") != record["sha256"]:
            raise PermissionError("Raw archive changed")
    output = DIRECTORY / "out/U01_step6_exit_day_corrected"
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "STARTED.json", {"started_utc": datetime.now(UTC).isoformat(),
               "source_sha256": manifest, "registration": registration,
               "runtime": {"python": platform.python_version(), "pandas": pd.__version__, "numpy": np.__version__}})
    for name, expected in manifest.items():
        target = output / "source" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / name).read_bytes())
        if digest(target) != expected:
            raise PermissionError("Source snapshot mismatch")
    write_json(output / "DATA_MANIFEST.json", data_manifest)
    bars = pd.read_pickle(CACHE / "validated.pkl")
    print(f"Preparing closed-timeframe features on {len(bars):,} M5 bars", flush=True)
    prepared = features(bars, protocol)
    signal, audit = signals(bars, prepared, protocol)
    # Ignore warm-up setups before the first research era in descriptive counts.
    audit = audit.loc[audit.setup_available_at.ge(pd.Timestamp(protocol["eras_exclusive_end"]["A"][0]))].copy()
    audit.to_csv(output / "setup_decisions.csv.gz", index=False, compression="gzip")
    frames, baseline_frames, eras, samplers = [], [], {}, {}
    audit_traded = set()
    for number, (era, bounds) in enumerate(protocol["eras_exclusive_end"].items()):
        pool = outcome_pool(bars, prepared, protocol, era, bounds)
        trades, initial = select_schedule(pool, signal, protocol["execution"]["daily_halt_r"])
        trades.to_csv(output / f"{era}_trades.csv", index=False)
        frames.append(trades)
        audit_traded.update(trades.entry_index.tolist())
        eras[era] = statistics(trades)
        print(f"{era}: {len(trades)} signal trades; {len(pool):,} eligible baseline outcomes", flush=True)
        if trades.empty:
            samplers[era] = {"mixing_warning": True, "status": "NO_OBSERVED_TRADES"}
            continue
        baseline, diagnostics = sample_schedules(pool, initial_ids=initial,
            draws=protocol["baseline_draws"], sweeps=protocol["baseline_sweeps"],
            seed=protocol["baseline_seed"] + number * 1000,
            daily_halt_r=protocol["execution"]["daily_halt_r"])
        for _, draw in baseline.groupby("draw"):
            if not schedule_is_valid(draw, daily_halt_r=protocol["execution"]["daily_halt_r"]):
                raise AssertionError("Invalid baseline schedule")
            if draw.dir.value_counts().to_dict() != trades.dir.value_counts().to_dict():
                raise AssertionError("Baseline BUY/SELL quota mismatch")
        samplers[era] = sampler_statistics(diagnostics, pool, trades, protocol)
        baseline.to_csv(output / f"{era}_baseline.csv.gz", index=False, compression="gzip")
        diagnostics.to_csv(output / f"{era}_sampler_diagnostics.csv", index=False)
        baseline_frames.append(baseline)
        print(f"{era}: {protocol['baseline_draws']} matched schedules validated", flush=True)
    trades = pd.concat(frames, ignore_index=True).sort_values("entry_index")
    trades.to_csv(output / "trades.csv", index=False)
    audit["executed_in_simulation"] = audit.entry_index.isin(audit_traded)
    audit.to_csv(output / "setup_decisions.csv.gz", index=False, compression="gzip")
    result = {"candidate_id": protocol["candidate_id"], "approval": False, "holdout_access": False,
              "eras": eras, "pooled": statistics(trades), "samplers": samplers,
              "setup_decisions": {str(k): int(v) for k, v in audit.reason.value_counts().items()},
              "h1_complete_bars": len(prepared["h1"]), "m15_complete_bars": len(prepared["m15"]),
              "by_direction": {d: statistics(trades.loc[trades.dir.eq(d)]) for d in ("BUY", "SELL")},
              "source_sha256": manifest, "protocol_sha256": registration["protocol_sha256"],
              "correction": json.loads((DIRECTORY / "CORRECTION.json").read_text())}
    if trades.empty:
        result.update(status="INSUFFICIENT_DATA", evaluation_complete=False, gates={}, bootstrap=None,
                      not_evaluated=[f"G{i}" for i in range(1, 10)])
    else:
        baseline = pd.concat(baseline_frames, ignore_index=True)
        bootstrap = paired_month_bootstrap(trades, baseline,
            start=protocol["eras_exclusive_end"]["A"][0], end="2025-12-31T23:59:59Z",
            resamples=protocol["bootstrap_resamples"], seed=protocol["bootstrap_seed"])
        years = (pd.Timestamp("2026-01-01T00:00Z") - pd.Timestamp("2005-06-01T00:00Z")).total_seconds() / (365.2425 * 86400)
        risk = monte_carlo_drawdown(trades.pnl_usd.to_numpy(), trades_per_year=max(1, round(len(trades) / years)),
                                   simulations=protocol["monte_carlo_paths"], seed=protocol["monte_carlo_seed"])
        inputs = {"account_usd": protocol["account_usd"], "bootstrap_lower_bound": bootstrap["mean_lower"],
                  "signal_minus_baseline": bootstrap["edge_point"], "edge_lower_bound": bootstrap["edge_lower"],
                  "positive_eras": sum(x["mean_r"] is not None and x["mean_r"] > 0 for x in eras.values()),
                  "baskets": len(trades), "gap_risk_share": result["pooled"]["gap_risk_share"],
                  "mc_p99_drawdown_usd": risk.p99_max_drawdown_usd, "max_fill_delta_pp": 0., "atr_parity": False}
        verdict = evaluate_gates(inputs, load_yaml(ROOT / "goldnix/gates/rules.yaml"))
        gates = verdict.gates
        gates["G9"].update(status="NOT_VERIFIED", value=None)
        warning = any(s["mixing_warning"] for s in samplers.values())
        numerical_failures = [g for g, v in gates.items() if g != "G9" and not v["passed"]]
        result.update(status="FAIL_WITH_G9_UNVERIFIED" if numerical_failures else "PROVISIONAL_G9_UNVERIFIED",
            evaluation_complete=False, historical_statistics_complete=True, not_evaluated=["G9"], gates=gates,
            gate_inputs=inputs, numerical_failures=numerical_failures, bootstrap=bootstrap,
            sampler_has_warning=warning, selection_bound=selection_bound(trades, protocol),
            monte_carlo={"paths": risk.simulations, "trades_per_year": risk.trades_per_year,
                         "p99_drawdown_usd": risk.p99_max_drawdown_usd, "observed_rate_per_year": len(trades) / years},
            extra_cost_fixed_schedule={str(cost): {"mean_r": float((trades.r_multiple - cost).mean()),
                "pnl_usd": float(trades.pnl_usd.sum() - len(trades) * cost * protocol["usd_per_price_unit"])}
                for cost in (.25, .50)})
    preserved_freezes()
    if sources() != manifest or digest(CACHE / "validated.pkl") != data_manifest["validated_sha256"]:
        raise PermissionError("Research source or input changed during evaluation")
    result["completed_utc"] = datetime.now(UTC).isoformat()
    write_json(output / "RESULT.json", result)
    (output / "REPORT.md").write_text(report_markdown(result))
    artifacts = {p.relative_to(output).as_posix(): digest(p) for p in sorted(output.rglob("*")) if p.is_file()}
    write_json(output / "FROZEN.json", {"completed_utc": result["completed_utc"], "status": result["status"],
               "artifact_sha256": artifacts, "approval": False})
    print(json.dumps({k: result[k] for k in ("status", "pooled", "gates")}), flush=True)


if __name__ == "__main__":
    main()
