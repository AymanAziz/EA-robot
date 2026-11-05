"""Replay only genuinely timestamped forward observations, with estimated historical fills.

This is research, not an assertion that a paper broker executed these trades. No
LLM is queried retrospectively; missing AI stays missing and the quant benchmark
uses the same observation grid. The existing quant backtest and risk functions
remain untouched and continue to govern execution timing, costs and exposure.
"""
from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from papertrade.ai.fusion import (_timestamp, ai_entry_agrees, seal_certificate, strategy_policy)
from papertrade.backtest import performance_metrics, run_backtest
from papertrade.config import Settings
from papertrade.data import validate_candles
from papertrade.decisions import decide
from papertrade.domain import Instrument, Quote, utcnow
from papertrade.features import build_features, feature_regime


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False, default=str).encode()).hexdigest()


def _benchmark(candles, instrument, settings, start, end):
    frame = candles.loc[start:end]
    if len(frame) < 2:
        return {"metrics": {}, "source": "estimated_buy_and_hold_benchmark"}
    spread = instrument.max_spread_bps / 2
    impact = (spread / 2 + instrument.slippage_bps) / 10000
    fee = instrument.fee_bps / 10000
    price = float(frame.open.iloc[1]) * (1 + impact)
    allocation = min(settings.max_instrument_exposure, instrument.max_exposure)
    qty = math.floor(settings.capital * allocation / (price * (1 + fee)) / instrument.qty_step) * instrument.qty_step
    if qty < instrument.min_qty:
        qty = 0
    entry_fee = qty * price * fee
    cash = settings.capital - qty * price - entry_fee
    equity = cash + qty * frame.close * (1 - spread / 20000)
    equity.iloc[0] = settings.capital
    exit_price = float(frame.close.iloc[-1]) * (1 - impact)
    exit_fee = qty * exit_price * fee
    equity.iloc[-1] = cash + qty * exit_price - exit_fee
    net = qty * (exit_price - price) - entry_fee - exit_fee
    costs = entry_fee + exit_fee + qty * (price - float(frame.open.iloc[1])) + qty * (float(frame.close.iloc[-1]) - exit_price)
    return {"metrics": performance_metrics(equity, [{"net_pl": net}] if qty else [],
                turnover=qty * (price + exit_price), exposure_bars=len(frame) - 1 if qty else 0,
                transaction_costs=costs), "source": "estimated_buy_and_hold_benchmark",
            "capital_allocation": allocation}


def _bootstrap_lower(trades):
    profits = np.asarray([trade["net_pl"] for trade in trades], dtype=float)
    if len(profits) < 5:
        return None
    # Circular blocks retain some short-run dependence; this remains only a diagnostic.
    block = max(2, int(np.sqrt(len(profits))))
    generator = np.random.default_rng(42)
    starts = generator.integers(0, len(profits), size=(1000, math.ceil(len(profits) / block)))
    indices = (starts[:, :, None] + np.arange(block)[None, None, :]) % len(profits)
    means = profits[indices.reshape(1000, -1)[:, :len(profits)]].mean(axis=1)
    return float(np.quantile(means, .025))


def evaluate_strategies(candles: pd.DataFrame, observations: list[dict], instrument: Instrument,
                        settings: Settings, *, now: datetime | None = None) -> dict:
    now = now or utcnow()
    frame = validate_candles(candles, now, instrument.market)
    features = build_features(frame)
    usable, excluded = [], Counter()
    for item in observations:
        try:
            if item.get("symbol") != instrument.symbol:
                excluded["wrong_symbol"] += 1
                continue
            if item.get("source") != "forward_observation":
                excluded["source_not_forward_observation"] += 1
                continue
            candle = pd.Timestamp(_timestamp(item["candle_at"]))
            decision = _timestamp(item["decision_at"])
            data_end = _timestamp(item["quant_data_end"])
            trained_at = _timestamp(item["quant_trained_at"])
            threshold = float(item["quant_threshold"])
            if item.get("quant_model_accepted") is not True or not .5 <= threshold <= 1:
                excluded["training_or_missing_quant_provenance"] += 1
                continue
            venue = "local_simulator" if settings.execution == "simulator" else "broker_paper"
            if item.get("execution_venue") != venue:
                excluded["different_or_missing_execution_venue"] += 1
                continue
            model = item.get("quant_model_version", item.get("model_version"))
            if not model or candle.to_pydatetime() <= data_end or trained_at > decision:
                excluded["training_or_missing_quant_provenance"] += 1
                continue
            close = candle.to_pydatetime() + timedelta(minutes=15)
            if not close <= decision <= close + timedelta(seconds=60) or decision > now:
                excluded["late_or_hindsight_quant_observation"] += 1
                continue
            outcome = candle + pd.Timedelta(minutes=75)
            if candle not in frame.index or outcome not in frame.index or outcome > frame.index[-1]:
                excluded["missing_or_unmatured_outcome"] += 1
                continue
            probability, expected = float(item["probability"]), float(item["expected_return"])
            if not np.isfinite([probability, expected]).all() or not 0 <= probability <= 1:
                excluded["invalid_quant_prediction"] += 1
                continue
            usable.append(dict(item, candle_at=candle, decision_at=decision, quant_model_version=model,
                               probability=probability, expected_return=expected, quant_threshold=threshold))
        except (ValueError, TypeError, KeyError, OverflowError):
            excluded["training_or_missing_quant_provenance"] += 1
    usable.sort(key=lambda item: item["candle_at"])
    if len(usable) < 10:
        raise ValueError("At least ten matured, unseen, timestamped forward observations are required")
    if len({item["candle_at"] for item in usable}) != len(usable):
        raise ValueError("Duplicate observations cannot be selected retrospectively")
    models = {item["quant_model_version"] for item in usable}
    if len(models) != 1:
        raise ValueError("Evaluate one quantitative model version at a time")
    identities = {(item.get("ai_provider", ""), item.get("ai_model", "")) for item in usable
                  if item.get("ai_provider") and item.get("ai_model")}
    if len(identities) > 1:
        raise ValueError("Evaluate one AI provider and model at a time")
    thresholds = {item["quant_threshold"] for item in usable}
    if len(thresholds) != 1:
        raise ValueError("Quantitative model thresholds must be frozen for an evaluation")
    threshold = next(iter(thresholds))
    provider, ai_model = next(iter(identities)) if identities else ("", "")
    observations_digest = _digest([{key: value.isoformat() if hasattr(value, "isoformat") else value
                                   for key, value in item.items()} for item in usable])
    probabilities = pd.Series(np.nan, index=frame.index)
    expected_returns = pd.Series(np.nan, index=frame.index)
    variant_probabilities = {name: probabilities.copy() for name in ("ai_filtered_quant", "hybrid")}
    ai_counts = Counter({"ai_filtered_quant": 0, "hybrid": 0})
    for item in usable:
        stamp = item["candle_at"]
        probability, expected = item["probability"], item["expected_return"]
        probabilities.loc[stamp], expected_returns.loc[stamp] = probability, expected
        feature = features.loc[stamp] if stamp in features.index else None
        mid = float(frame.loc[stamp, "close"])
        spread = instrument.max_spread_bps / 2
        quote = Quote(mid * (1 - spread / 20000), mid * (1 + spread / 20000), item["decision_at"])
        # Existing reducing exits remain quantitative. NaN masks only potential entries,
        # because decide(NaN, ...) returns HOLD rather than manufacturing an exit.
        reducing = decide(probability, expected, feature_regime(feature) if feature is not None else "unknown",
                          instrument, quote, float(frame.loc[stamp, "volume"]), 1., settings).action == "CLOSE"
        for name, variant in variant_probabilities.items():
            agrees, _ = ai_entry_agrees(item.get("ai_response"), strategy=name, symbol=instrument.symbol,
                candle_at=stamp.to_pydatetime(), decision_at=item["decision_at"],
                ai_created_at=item.get("ai_created_at"), max_age_minutes=getattr(settings, "ai_max_age_minutes", 75))
            # The modeled fill occurs at candle close, before a second-20 decision.
            # Later AI cannot retroactively authorize that open-price execution.
            try:
                if _timestamp(item.get("ai_created_at")) > stamp.to_pydatetime() + timedelta(minutes=15):
                    agrees = False
            except (ValueError, TypeError):
                agrees = False
            if (item.get("ai_provider"), item.get("ai_model")) != (provider, ai_model):
                agrees = False
            ai_counts[name] += int(agrees)
            variant.loc[stamp] = probability if agrees or reducing else np.nan
    cut = usable[int(len(usable) * .6)]["candle_at"]
    validation_rows = [row for row in usable if row["candle_at"] + pd.Timedelta(minutes=75) < cut]
    test_rows = [row for row in usable if row["candle_at"] >= cut]
    if len(validation_rows) < 2 or len(test_rows) < 2:
        raise ValueError("Insufficient nonoverlapping chronological validation/test partitions")
    partitions = {"validation": (validation_rows[0]["candle_at"], validation_rows[-1]["candle_at"] + pd.Timedelta(minutes=75)),
                  "test": (test_rows[0]["candle_at"], test_rows[-1]["candle_at"] + pd.Timedelta(minutes=75))}
    all_probabilities = {"quant_only": probabilities, **variant_probabilities}
    # The rule benchmark has the identical decision-observation grid.
    rule = pd.Series(np.where((features.sma20_gap > 0) & (features.return_4 > 0) &
                             (features.regime == 1) & (features.rsi14 < 80), .99, .01), index=features.index)
    rule = rule.reindex(frame.index).where(probabilities.notna())
    rule_expected = features.return_4.reindex(frame.index).where(probabilities.notna())
    results, benchmarks = {}, {}
    for partition, (start, end) in partitions.items():
        benchmarks[partition] = {
            "rule": run_backtest(frame, rule, instrument, expected_returns=rule_expected,
                                  start=start, end=end, settings=settings, now=now),
            "buy_hold": _benchmark(frame, instrument, settings, start, end)}
        for name, series in all_probabilities.items():
            report = run_backtest(frame, series, instrument, expected_returns=expected_returns,
                                  start=start, end=end, settings=settings, threshold=threshold, now=now)
            report["source"] = "forward_replay"
            results.setdefault(name, {})[partition] = report
    minimum_trades = getattr(settings, "strategy_min_validation_trades", 30)
    minimum_observations = getattr(settings, "strategy_min_observations", 96)
    for name, result in results.items():
        validation, test = result["validation"]["metrics"], result["test"]["metrics"]
        lower = _bootstrap_lower(result["test"]["trades"])
        factor = test["profit_factor"]
        checks = {
            "minimum genuine forward observations": len(usable) >= minimum_observations,
            "minimum validation closed trades": validation["trade_count"] >= minimum_trades,
            "minimum test closed trades": test["trade_count"] >= minimum_trades,
            "positive validation return after estimated costs": validation["total_return"] > 0,
            "positive test return after estimated costs": test["total_return"] > 0,
            "positive test Sharpe": test["sharpe"] > 0,
            "test profit factor above one": factor is None or factor > 1,
            "maximum validation drawdown": validation["max_drawdown"] >= -settings.max_drawdown,
            "maximum test drawdown": test["max_drawdown"] >= -settings.max_drawdown,
            "positive block bootstrap lower mean P/L": lower is not None and lower > 0,
            "outperform rule benchmark": test["total_return"] > benchmarks["test"]["rule"]["metrics"]["total_return"],
            "outperform capped buy-and-hold": test["total_return"] > benchmarks["test"]["buy_hold"]["metrics"]["total_return"],
        }
        if name != "quant_only":
            checks.update({
                "minimum timely agreeing AI observations": ai_counts[name] >= minimum_observations,
                "AI provider and model provenance": bool(provider and ai_model),
                "improve validation over quant only": validation["total_return"] > results["quant_only"]["validation"]["metrics"]["total_return"],
                "improve test over quant only": test["total_return"] > results["quant_only"]["test"]["metrics"]["total_return"],
            })
        result.update(accepted=all(checks.values()), criteria=checks,
                      validation_failures=[key for key, passed in checks.items() if not passed],
                      bootstrap_mean_pl_lower_95=lower)
    results["ai_only_research"] = {"metrics": None, "accepted": False, "execution_enabled": False,
        "reason": "AI opinions have no independently calibrated expected-return strategy; recommendations only"}
    policy = strategy_policy(settings)
    return {"schema_version": 1, "source": "forward_replay", "symbol": instrument.symbol,
            "source_label": "Replay of timestamped forward observations with estimated fills; not actual broker-paper results",
            "quant_model_version": next(iter(models)), "ai_provider": provider, "ai_model": ai_model,
            "quant_threshold": threshold,
            "execution_venue_observed": "local_simulator" if settings.execution == "simulator" else "broker_paper", "observations": len(usable),
            "ai_usable_observations": dict(ai_counts), "excluded": dict(excluded),
            "observations_sha256": observations_digest, "policy_sha256": policy["sha256"],
            "split": {name: {"start": start.isoformat(), "end": end.isoformat()} for name, (start, end) in partitions.items()},
            "strategies": results, "benchmarks": benchmarks,
            "limitations": ["No retrospective LLM calls; current AI cannot create historical evidence",
                            "Fixed declared gates; reusing acceptance periods is not a fresh test",
                            "Estimated next-open execution differs from second-20 decisions and actual broker fills",
                            "AI arriving after the modeled next-open fill cannot authorize that entry",
                            "Per-symbol isolated portfolios; operational global risk may veto additional trades",
                            "Block bootstrap is an approximate diagnostic, not proof of future profitability"]}


def build_certificate(report: dict, strategy: str, quant_model_version: str, provider: str,
                      model: str, settings: Settings, now: datetime | None = None) -> dict:
    now = now or utcnow()
    if strategy not in {"quant_only", "ai_filtered_quant", "hybrid"}:
        raise ValueError("Research-only strategy cannot receive execution approval")
    if (report.get("source") != "forward_replay" or report.get("quant_model_version") != quant_model_version
            or report.get("ai_provider") != provider or report.get("ai_model") != model
            or report.get("policy_sha256") != strategy_policy(settings)["sha256"]):
        raise ValueError("Report provenance or current strategy policy does not match")
    result = report["strategies"][strategy]
    accepted = result.get("accepted") is True and bool(result.get("criteria")) and all(v is True for v in result["criteria"].values())
    candidate = {"schema_version": 1, "strategy": strategy, "symbol": report["symbol"],
        "quant_model_version": quant_model_version, "ai_provider": provider, "ai_model": model,
        "policy_sha256": report["policy_sha256"], "report_sha256": _digest(report),
        "source": "forward_replay", "accepted": accepted, "approved": False,
        "criteria": result["criteria"], "validation_failures": result.get("validation_failures", []),
        "created_at": now.isoformat(), "approved_at": None,
        "expires_at": (now + timedelta(days=getattr(settings, "strategy_certificate_max_age_days", 30))).isoformat(),
        "split": report["split"], "observations_sha256": report["observations_sha256"]}
    return seal_certificate(candidate)


def approve_certificate(candidate: dict, now: datetime | None = None) -> dict:
    now = now or utcnow()
    if candidate.get("content_sha256") != seal_certificate(candidate)["content_sha256"]:
        raise ValueError("Candidate integrity check failed")
    if (candidate.get("accepted") is not True or not candidate.get("criteria")
            or not all(value is True for value in candidate["criteria"].values())):
        raise ValueError("Candidate did not pass validation")
    if not _timestamp(candidate["created_at"]) <= now < _timestamp(candidate["expires_at"]):
        raise ValueError("Candidate expired or has future provenance")
    return seal_certificate(dict(candidate, approved=True, approved_at=now.isoformat()))
