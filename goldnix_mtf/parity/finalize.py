"""Combine immutable historical statistics and new native parity evidence."""

import json
from datetime import UTC, datetime
from pathlib import Path

from gates.verdict import evaluate_gates
from goldnix_mtf.data import ROOT, digest
from params.config import load_yaml


def main():
    directory = ROOT / "goldnix_mtf"
    historical = directory / "out/U01_step6_exit_day_corrected"
    native = ROOT / json.loads((directory / "parity/LATEST.json").read_text())["directory"]
    result = json.loads((historical / "RESULT.json").read_text())
    parity = json.loads((native / "RESULT.json").read_text())
    if not parity["passed"]:
        raise ValueError("New M5 parity has not passed")
    for name, expected in json.loads((historical / "FROZEN.json").read_text())["artifact_sha256"].items():
        if digest(historical / name) != expected:
            raise PermissionError("Historical artifact changed")
    for name, expected in parity["input_sha256"].items():
        if digest(native / name) != expected:
            raise PermissionError("Native input changed")
    output = directory / "out/U01_final_review"
    output.mkdir(exist_ok=False)
    inputs = {**result["gate_inputs"], "atr_parity": True}
    verdict = evaluate_gates(inputs, load_yaml(ROOT / "goldnix/gates/rules.yaml"))
    result.update(status="STEP6_EVALUATED_NOT_APPROVED", evaluation_complete=True, not_evaluated=[],
                  gates=verdict.gates, gate_inputs=inputs, numerical_gate_verdict=verdict.verdict,
                  finalized_utc=datetime.now(UTC).isoformat(), approval=False,
                  g9_evidence=str(native.relative_to(ROOT) / "RESULT.json"),
                  g9_evidence_sha256=digest(native / "RESULT.json"),
                  historical_result_sha256=digest(historical / "RESULT.json"),
                  finalizer_sha256=digest(__file__))
    (output / "RESULT.json").write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n")
    total = result["pooled"]
    boot = result["bootstrap"]
    lines = ["# Step 6 result: user's multi-timeframe method", "",
        "**This version does not pass Step 6.** All nine checks now have evidence, including the new "
        "read-only MT5 parity check. The formal gate verdict is **INSUFFICIENT_DATA** because G5 requires "
        "1,000 trades; the profitability and random-entry edge gates also fail.", "",
        "This evaluates one registered interpretation of the user's method, with explicit starting parameters. "
        "It does not disprove every multi-timeframe or retest strategy. No settings were optimized after results.", "",
        "## Rules tested", "",
        "1. H1 trend: closed price versus EMA50, with the EMA slope over three closed H1 candles. BUY and SELL mirror each other.",
        "2. M15 setup: a completed pullback through EMA20 and close back on the trend side. Freeze that candle's high for BUY or low for SELL.",
        "3. M5 confirmation: the next candle closes beyond the level by a buffer; the following candle retests the level band and reclaims it. Reject late, missing or extended confirmations.",
        "4. Enter on the next boundary quote; fixed 1-price-unit stop, five-minute exit, 0.01oz exposure. "
        "Actual bid/ask sides, one position, a conservative position slot, Friday/holiday exclusions and "
        "the original Step6 -2R UTC daily halt apply.", "",
        "EMA periods, buffer, expiry and stop/time rules are declared implementation assumptions. "
        "The method uses price; provider volume units are undocumented, so no volume filter was added. "
        "[Exact frozen protocol](../U01_step6_exit_day_corrected/source/goldnix_mtf/protocol.json).", "",
        "## Historical result: 2005–2025", "",
        "| Era | Trades | BUY | SELL | Win rate | Mean R | P/L at 0.01oz (USD) |",
        "|---|---:|---:|---:|---:|---:|---:|"]
    for name, stats in [*result["eras"].items(), ("Total", total)]:
        lines.append(f"| {name} | {stats['trades']} | {stats['buy_trades']} | {stats['sell_trades']} | "
                     f"{stats['win_rate']:.1%} | {stats['mean_r']:.4f} | {stats['pnl_usd']:.4f} |")
    lines += ["", "Era A: Jun 2005–Aug 2011; B: Sep 2011–2015; C: 2016–2020; D: 2021–2025.", "",
        f"Profit factor: **{total['profit_factor']:.3f}**. Simulated total loss: **${-total['pnl_usd']:.4f}** "
        f"(approximately **{-total['pnl_usd'] * 100:.2f} USC**) at the currently verified Cent contract size. "
        f"Realized historical maximum drawdown: **${total['max_drawdown_usd']:.4f}**. "
        "These are simulated historical outcomes, not the current demo account's transactions.", "",
        f"Mean expectancy: **{total['mean_r']:.4f}R**; one-sided 95% lower bound **{boot['mean_lower']:.4f}R**. "
        f"Matched random-entry mean: **{boot['baseline_mean']:.4f}R**. "
        f"Method minus random: **{boot['edge_point']:.4f}R**, lower bound **{boot['edge_lower']:.4f}R**. "
        "The comparison used 200 feasible schedules per era, matched BUY/SELL counts and loss controls, "
        "and 10,000 paired calendar-month bootstrap resamples.", "",
        "R is the nominal one-unit stop. Spread is already included; a stop can lose more than 1R. "
        "The USD result uses 0.01oz and does not establish historical JustMarkets pricing, margin or costs.", "",
        "## All nine gates", "", "| Gate | Result | Value | Requirement |", "|---|---|---:|---|"]
    for name, gate in result["gates"].items():
        value = gate["value"]
        rendered = f"{value:.6f}" if isinstance(value, float) else str(value)
        lines.append(f"| {name} | {'PASS' if gate['passed'] else 'FAIL'} | {rendered} | {gate['rule']} |")
    lines += ["", "G1: expectancy lower bound; G2: edge over random; G3: edge lower bound; G4: profitable eras; "
        "G5: trade count; G6: gap-risk share; G7: 99th-percentile one-year USD drawdown; "
        "G8: stop-first/target-first win-rate difference; G9: indicator parity.", "",
        "G7 used 100,000 IID one-year paths on a USD20 account. It is not a margin, ruin or unseen-tail model. "
        "G8 is zero by construction because this version has no take profit; this is not evidence of tick-level "
        "execution accuracy. G9 compares 200 closed native bars after 800 warm-up bars: M5 ATR14, H1 EMA50, "
        "M15 EMA20, closed-bar availability and complete M5-to-higher-timeframe OHLC aggregates. "
        "It does not validate historic spreads or order fills.", "",
        f"Sampler diagnostic warning: **{result['sampler_has_warning']}**. Finite MCMC diagnostics cannot prove convergence. "
        f"The additional 69-variant selection lower bound is **{result['selection_bound']['mean_lower']:.4f}R**; "
        "it is only a disclosure of repeated research, with a noisy extreme bootstrap tail.", "",
        "## What to conclude", "",
        "The new logic can SELL as well as BUY. Under this exact confirmation, fixed stop and five-minute exit, "
        "it did not demonstrate a positive edge after spread. Its strict setup also produced too few trades "
        "for the original minimum. Adding confirmations alone did not make this version qualify.", "",
        "The rejection counts are filter decisions, not proof that fakeouts were reduced versus an unfiltered "
        "strategy. That incremental question needs a separately registered matched comparison. Commissions, "
        "financing and intrabar stop slippage remain outside the spread-based historical model. No optimization "
        "or new forward execution is authorized by this result.", "",
        "This is registered candidate 69 on previously examined history. No 2026 holdout performance was "
        "evaluated. Recent broker price exports were used only for indicator and timestamp parity. The original "
        "demo scripts and frozen V1/V2 results were preserved. The first historical attempt remains archived; "
        "a midnight stop-day accounting fix changed no strategy parameters and left the 788 strategy trades unchanged.", "",
        "Validation: 36 behavioral/statistical tests passed; all 788 trade records, 800 baseline schedules and "
        "both historical artifact manifests were independently checked. The native exporter compiled with "
        "zero errors and warnings. Its first H1 export lacked initialized history; the retry requested the "
        "necessary warm-up history and retained the same sample size and tolerances.", "",
        "## Review artifacts", "",
        "- [Full final metrics](RESULT.json)",
        "- [Every simulated trade](../U01_step6_exit_day_corrected/trades.csv)",
        "- [Every setup decision](../U01_step6_exit_day_corrected/setup_decisions.csv.gz)",
        f"- [New native MT5 parity evidence](../../parity/out/{native.name}/RESULT.json)",
        "- [Independent verification receipt](../verification/RECEIPT.json)",
        "- [Historical data hashes](../U01_step6_exit_day_corrected/DATA_MANIFEST.json)", "",
        "Data attribution: [EVTradingLabs](https://evtradelabs.com/data), whose catalogue attributes underlying "
        "ticks to Dukascopy. 21 public annual files supplied 1,511,699 M5 bid/ask bars; raw-source provenance is "
        "the publisher's claim. Missing intervals were retained as gaps, not interpolated.", ""]
    (output / "REPORT.md").write_text("\n".join(lines))
    evidence = {str(p.relative_to(ROOT)): digest(p) for p in
        [*native.rglob("*.csv"), *native.rglob("*.json"), *native.rglob("*.mq5"), *native.rglob("*.ex5"),
         historical / "FROZEN.json", historical / "RESULT.json", directory / "out/verification/RECEIPT.json",
         Path(__file__), directory / "parity/check.py", *output.iterdir()] if p.is_file()}
    (output / "FROZEN.json").write_text(json.dumps({"created_utc": result["finalized_utc"],
        "artifact_sha256_from_repo_root": evidence, "approval": False}, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"report": str(output / "REPORT.md"), "status": result["status"],
                      "gate_verdict": verdict.verdict, "gates": verdict.gates}, indent=2))


if __name__ == "__main__":
    main()
