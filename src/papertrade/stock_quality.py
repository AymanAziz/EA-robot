"""Research-only developed-market profitability-quality evaluation.

This module consumes published Kenneth French portfolio returns.  It is
deliberately isolated from settings, persistence, brokers, the trading engine,
and order submission.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import io
import json
import math
import os
import zipfile
from csv import reader as csv_reader
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

import httpx
import numpy as np
import pandas as pd


SOURCE_ID = "kenneth_french_developed_daily_quality_v1"
DEVELOPED_FACTORS_DAILY_URL = (
    "https://mba.tuck.dartmouth.edu/pages/faculty/Ken.French/ftp/"
    "Developed_5_Factors_Daily_CSV.zip"
)
DEVELOPED_PROFITABILITY_DAILY_URL = (
    "https://mba.tuck.dartmouth.edu/pages/faculty/Ken.French/ftp/"
    "Developed_6_Portfolios_ME_OP_Daily_CSV.zip"
)
DEVELOPED_FACTORS_DAILY_SHA256 = (
    "f6c5ceea945f4c2829025fc654d6a878041eba85765c88ee05ba34640f622831"
)
DEVELOPED_PROFITABILITY_DAILY_SHA256 = (
    "4cc284b9bd6450f4e3717fe8e1824efefef3d53af1c7caaa9dc02c2c14824433"
)
EVIDENCE_WARNING = (
    "Locked retrospective evidence from historically formed published portfolios; "
    "not constituent-level reconstruction, not a broker paper fill, and not proof "
    "of future weekly profit or an executable trade."
)


def _json_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_value(item) for item in value]
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float):
        if np.isnan(value):
            return None
        if not np.isfinite(value):
            raise ValueError("Stock-quality evidence cannot contain infinity")
    return value


def _canonical_json(value: Any) -> str:
    return json.dumps(
        _json_value(value), sort_keys=True, separators=(",", ":"), allow_nan=False
    )


@dataclass(frozen=True)
class StockQualityHistory:
    """Normalized aligned daily rows plus immutable source provenance."""

    rows: tuple[Mapping[str, Any], ...]
    manifest: tuple[Mapping[str, Any], ...]
    payloads: tuple[bytes, ...] = ()

    def __post_init__(self):
        object.__setattr__(
            self, "rows", tuple(MappingProxyType(dict(row)) for row in self.rows)
        )
        object.__setattr__(
            self,
            "manifest",
            tuple(MappingProxyType(dict(item)) for item in self.manifest),
        )
        object.__setattr__(self, "payloads", tuple(bytes(item) for item in self.payloads))


@dataclass(frozen=True)
class StockQualityStrategySpec:
    """Immutable preregistration for the single stock-quality hypothesis."""

    strategy_version: str = "developed_market_big_robust_80_20_v1"
    portfolio_rule: str = "80% developed market; 20% value-weighted Big Robust"
    benchmark_rule: str = "100% developed market reconstructed as Mkt-RF plus RF"
    rebalance_rule: str = "close of first common observation in Jan/Apr/Jul/Oct"
    weekly_block_rule: str = "consecutive seven-calendar-day blocks anchored at test start"
    bootstrap_rule: str = "paired circular blocks; floor(sqrt(weeks)); 10000 samples; seed 42"
    cost_rule: str = (
        "10 bps per one-way traded notional at entry, rebalance, and final liquidation"
    )
    annual_drag_rule: str = "actual calendar days divided by 365.2425"
    initial_equity_usd: float = 10_000.0
    developed_market_weight: float = 0.80
    big_robust_weight: float = 0.20
    market_annual_drag: float = 0.0010
    big_robust_annual_drag: float = 0.0050
    transaction_cost_bps: float = 10.0
    target_weekly_profit_usd: float = 20.0
    minimum_complete_weeks: int = 260
    minimum_profitable_week_fraction: float = 0.50
    bootstrap_samples: int = 10_000
    bootstrap_seed: int = 42
    bootstrap_quantile: float = 0.05
    test_a_start: date = date(1991, 7, 1)
    test_a_end: date = date(2007, 12, 31)
    test_b_start: date = date(2008, 1, 1)
    test_b_end: date = date(2025, 12, 31)

    def canonical_dict(self) -> dict[str, Any]:
        return _json_value(asdict(self))

    @property
    def sha256(self) -> str:
        return hashlib.sha256(_canonical_json(self.canonical_dict()).encode()).hexdigest()


def _is_daily_date(value: str) -> bool:
    return len(value) == 8 and value.isdigit()


def _daily_iso(value: str) -> str:
    try:
        return date(int(value[:4]), int(value[4:6]), int(value[6:8])).isoformat()
    except ValueError as exc:
        raise ValueError(f"Kenneth French daily file contains invalid date {value!r}") from exc


def _finite_percent(value: str, field: str) -> float:
    try:
        result = float(value.strip())
    except ValueError as exc:
        raise ValueError(f"Kenneth French {field} contains a nonnumeric return") from exc
    if not math.isfinite(result) or result <= -99.0:
        raise ValueError(f"Kenneth French {field} contains a missing-value sentinel")
    return result


def _factor_rows(text: str) -> dict[str, tuple[float, float]]:
    rows = list(csv_reader(io.StringIO(text)))
    header_index = next((
        index for index, row in enumerate(rows)
        if {item.strip().upper() for item in row}.issuperset({"MKT-RF", "RF"})
    ), None)
    if header_index is None:
        raise ValueError("Developed five-factor file is missing its daily header")
    header = [item.strip().upper() for item in rows[header_index]]
    market_index = header.index("MKT-RF")
    rf_index = header.index("RF")
    result: dict[str, tuple[float, float]] = {}
    for row in rows[header_index + 1:]:
        if not row or not _is_daily_date(row[0].strip()):
            if result:
                break
            continue
        stamp = _daily_iso(row[0].strip())
        if stamp in result:
            raise ValueError("Developed five-factor file contains a duplicate daily date")
        market_excess = _finite_percent(row[market_index], "Mkt-RF")
        risk_free = _finite_percent(row[rf_index], "RF")
        result[stamp] = (market_excess + risk_free, risk_free)
    if not result:
        raise ValueError("Developed five-factor file contains no daily returns")
    return result


def _big_robust_rows(text: str) -> dict[str, float]:
    rows = list(csv_reader(io.StringIO(text)))
    section_index = next((
        index for index, row in enumerate(rows)
        if "average value weighted returns -- daily" in " ".join(row).strip().lower()
    ), None)
    if section_index is None:
        raise ValueError("Developed profitability file is missing its value-weighted daily section")
    header_index = next((
        index for index in range(section_index + 1, len(rows))
        if len(rows[index]) >= 7 and not _is_daily_date(rows[index][0].strip())
    ), None)
    if header_index is None:
        raise ValueError("Developed profitability file is missing its daily portfolio header")
    normalized = [
        "".join(character for character in item.lower() if character.isalnum())
        for item in rows[header_index]
    ]
    candidates = [
        index for index, name in enumerate(normalized)
        if name in {"bighibo", "bighiop", "bigrobust", "br"}
    ]
    if len(candidates) != 1:
        raise ValueError("Developed profitability file does not identify one Big Robust column")
    big_robust_index = candidates[0]
    result: dict[str, float] = {}
    for row in rows[header_index + 1:]:
        if not row or not _is_daily_date(row[0].strip()):
            if result:
                break
            continue
        stamp = _daily_iso(row[0].strip())
        if stamp in result:
            raise ValueError("Developed profitability file contains a duplicate daily date")
        if len(row) <= big_robust_index:
            raise ValueError("Developed profitability daily row is truncated")
        result[stamp] = _finite_percent(row[big_robust_index], "Big Robust")
    if not result:
        raise ValueError("Developed profitability file contains no daily returns")
    return result


def _zip_csv_text(content: bytes) -> tuple[str, str]:
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            members = [name for name in archive.namelist() if name.lower().endswith(".csv")]
            if len(members) != 1:
                raise ValueError("Kenneth French ZIP must contain exactly one CSV member")
            member = members[0]
            text = archive.read(member).decode("utf-8-sig")
    except (zipfile.BadZipFile, UnicodeDecodeError) as exc:
        raise ValueError("Kenneth French response is not a valid UTF-8 CSV ZIP") from exc
    return member, text


def _aligned_source_rows(factor_text: str, profitability_text: str) -> tuple[dict[str, Any], ...]:
    factors = _factor_rows(factor_text)
    big_robust = _big_robust_rows(profitability_text)
    if factors.keys() != big_robust.keys():
        raise ValueError("Kenneth French daily sources do not have exactly aligned dates")
    return tuple({
        "date": stamp,
        "market_return_percent": factors[stamp][0],
        "big_robust_return_percent": big_robust[stamp],
        "risk_free_return_percent": factors[stamp][1],
    } for stamp in factors)


class KennethFrenchDevelopedHistory:
    """Keyless adapter for the two official Dartmouth daily ZIP files."""

    def __init__(self, client: httpx.Client | None = None):
        self._client = client or httpx.Client(
            timeout=30,
            follow_redirects=True,
            headers={"User-Agent": "papertrade-research/0.1"},
        )

    def _download(self, role: str, url: str) -> tuple[str, dict[str, Any], bytes]:
        response = self._client.get(url)
        response.raise_for_status()
        content = response.content
        response_sha256 = hashlib.sha256(content).hexdigest()
        member, text = _zip_csv_text(content)
        manifest = {
            "role": role,
            "url": url,
            "member": member,
            "response_sha256": response_sha256,
            "etag": response.headers.get("ETag"),
            "last_modified": response.headers.get("Last-Modified"),
        }
        return text, manifest, content

    def fetch(self) -> StockQualityHistory:
        factor_text, factor_manifest, factor_payload = self._download(
            "developed_five_factors_daily", DEVELOPED_FACTORS_DAILY_URL
        )
        profitability_text, profitability_manifest, profitability_payload = self._download(
            "developed_size_profitability_daily", DEVELOPED_PROFITABILITY_DAILY_URL
        )
        rows = _aligned_source_rows(factor_text, profitability_text)
        factor_manifest["returned_rows"] = len(rows)
        profitability_manifest["returned_rows"] = len(rows)
        return StockQualityHistory(
            rows=rows,
            manifest=(factor_manifest, profitability_manifest),
            payloads=(factor_payload, profitability_payload),
        )


def _prepare_history(
    history: StockQualityHistory, spec: StockQualityStrategySpec
) -> tuple[pd.DataFrame, str]:
    frame = pd.DataFrame(history.rows)
    required = {
        "date",
        "market_return_percent",
        "big_robust_return_percent",
        "risk_free_return_percent",
    }
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"Stock-quality history is missing required fields: {sorted(missing)}")
    provider_date = pd.to_datetime(frame.pop("date"), format="%Y-%m-%d", errors="raise")
    frame.index = pd.DatetimeIndex(provider_date, name="provider_date")
    if frame.empty:
        raise ValueError("Stock-quality history contains no rows")
    if not frame.index.is_unique or not frame.index.is_monotonic_increasing:
        raise ValueError("Stock-quality dates must be unique and strictly increasing")
    if frame.index.to_series().diff().gt(pd.to_timedelta(7, unit="D")).any():
        raise ValueError("Stock-quality history contains a gap greater than seven calendar days")
    columns = [
        "market_return_percent",
        "big_robust_return_percent",
        "risk_free_return_percent",
    ]
    frame[columns] = frame[columns].apply(pd.to_numeric, errors="raise")
    values = frame[columns].to_numpy(dtype=float)
    if not np.isfinite(values).all():
        raise ValueError("Stock-quality history requires finite returns")
    if (values <= -100.0).any():
        raise ValueError("Stock-quality history contains a return at or below -100%")
    if frame.index.min().date() > spec.test_a_start or frame.index.max().date() < spec.test_b_end:
        raise ValueError("Stock-quality history does not cover both locked evaluation windows")
    normalized = frame.rename(columns={column: column.removesuffix("_percent") for column in columns})
    normalized = normalized / 100.0
    records = frame.reset_index().copy()
    records["provider_date"] = records["provider_date"].dt.strftime("%Y-%m-%d")
    material = {
        "source_id": SOURCE_ID,
        "manifest": tuple(dict(item) for item in history.manifest),
        "rows": records.to_dict("records"),
    }
    digest = hashlib.sha256(_canonical_json(material).encode()).hexdigest()
    return normalized, digest


def _bootstrap_lower_means(
    weekly_pl: np.ndarray,
    weekly_excess_pl: np.ndarray,
    spec: StockQualityStrategySpec,
) -> tuple[float | None, float | None]:
    count = len(weekly_pl)
    if count < 2:
        return None, None
    block_length = max(2, int(math.sqrt(count)))
    blocks_needed = math.ceil(count / block_length)
    generator = np.random.default_rng(spec.bootstrap_seed)
    starts = generator.integers(0, count, size=(spec.bootstrap_samples, blocks_needed))
    offsets = np.arange(block_length)
    indices = (starts[..., None] + offsets) % count
    indices = indices.reshape(spec.bootstrap_samples, -1)[:, :count]
    target_means = weekly_pl[indices].mean(axis=1)
    excess_means = weekly_excess_pl[indices].mean(axis=1)
    return (
        float(np.quantile(target_means, spec.bootstrap_quantile)),
        float(np.quantile(excess_means, spec.bootstrap_quantile)),
    )


def _maximum_drawdown(values: pd.Series) -> float:
    running_high = values.cummax()
    return float((values / running_high - 1.0).min())


def _weekly_marks(
    daily: pd.DataFrame,
    start: date,
    end: date,
    initial_equity: float,
) -> dict[str, np.ndarray]:
    boundaries = []
    boundary = start + timedelta(days=7)
    while boundary <= end:
        boundaries.append(pd.Timestamp(boundary))
        boundary += timedelta(days=7)
    strategy_marks = [initial_equity]
    benchmark_marks = [initial_equity]
    cash_marks = [initial_equity]
    prior_observation = pd.Timestamp(start)
    for boundary in boundaries:
        eligible = daily.index[daily.index <= boundary]
        if len(eligible) == 0 or eligible[-1] <= prior_observation:
            raise ValueError("A complete weekly block has no new common source observation")
        observation = eligible[-1]
        strategy_marks.append(float(daily.at[observation, "strategy_equity_usd"]))
        benchmark_marks.append(float(daily.at[observation, "benchmark_equity_usd"]))
        cash_marks.append(float(daily.at[observation, "cash_equity_usd"]))
        prior_observation = observation
    strategy_returns = np.diff(strategy_marks) / np.asarray(strategy_marks[:-1])
    benchmark_returns = np.diff(benchmark_marks) / np.asarray(benchmark_marks[:-1])
    cash_returns = np.diff(cash_marks) / np.asarray(cash_marks[:-1])
    return {
        "strategy_pl": initial_equity * strategy_returns,
        "benchmark_pl": initial_equity * benchmark_returns,
        "cash_pl": initial_equity * cash_returns,
    }


def _self_financing_rebalance(
    market_value: float,
    quality_value: float,
    target_market_weight: float,
    cost_rate: float,
) -> tuple[float, float, float, float]:
    equity = market_value + quality_value
    lower_cost = 0.0
    upper_cost = equity * cost_rate
    for _ in range(100):
        cost = (lower_cost + upper_cost) / 2.0
        post_cost_equity = equity - cost
        target_market = post_cost_equity * target_market_weight
        target_quality = post_cost_equity * (1.0 - target_market_weight)
        traded_notional = 0.5 * (
            abs(target_market - market_value) + abs(target_quality - quality_value)
        )
        implied_cost = traded_notional * cost_rate
        if implied_cost > cost:
            lower_cost = cost
        else:
            upper_cost = cost
    cost = (lower_cost + upper_cost) / 2.0
    post_cost_equity = equity - cost
    target_market = post_cost_equity * target_market_weight
    target_quality = post_cost_equity * (1.0 - target_market_weight)
    traded_notional = 0.5 * (
        abs(target_market - market_value) + abs(target_quality - quality_value)
    )
    cost = traded_notional * cost_rate
    return target_market, target_quality, traded_notional, cost


def _window_result(
    frame: pd.DataFrame,
    start: date,
    end: date,
    spec: StockQualityStrategySpec,
) -> dict[str, Any]:
    last_boundary = start + timedelta(days=7 * ((end - start).days // 7))
    interval = frame[
        (frame.index >= pd.Timestamp(start)) & (frame.index <= pd.Timestamp(last_boundary))
    ]
    if len(interval) < 2:
        raise ValueError("Locked stock-quality window has insufficient common observations")
    initial = spec.initial_equity_usd
    cost_rate = spec.transaction_cost_bps / 10_000
    invested = initial / (1.0 + cost_rate)
    entry_cost = invested * cost_rate
    market_value = invested * spec.developed_market_weight
    quality_value = invested * spec.big_robust_weight
    benchmark_value = invested
    cash_value = initial
    portfolio_constraint_breached = False
    costs = [{
        "provider_date": interval.index[0].date().isoformat(),
        "event": "entry",
        "traded_notional_usd": invested,
        "cost_usd": entry_cost,
    }]
    records = [{
        "provider_date": interval.index[0],
        "strategy_equity_usd": market_value + quality_value,
        "benchmark_equity_usd": benchmark_value,
        "cash_equity_usd": cash_value,
    }]
    previous_date = interval.index[0]
    previous_quarter = (previous_date.year, previous_date.quarter)
    for provider_date, row in interval.iloc[1:].iterrows():
        calendar_days = (provider_date - previous_date).days
        market_fee_factor = 1.0 - spec.market_annual_drag * calendar_days / 365.2425
        quality_fee_factor = 1.0 - spec.big_robust_annual_drag * calendar_days / 365.2425
        market_value *= (1.0 + row["market_return"]) * market_fee_factor
        quality_value *= (1.0 + row["big_robust_return"]) * quality_fee_factor
        benchmark_value *= (1.0 + row["market_return"]) * market_fee_factor
        cash_value *= 1.0 + row["risk_free_return"]
        quarter = (provider_date.year, provider_date.quarter)
        if quarter != previous_quarter and provider_date != interval.index[-1]:
            (
                market_value,
                quality_value,
                one_way_notional,
                rebalance_cost,
            ) = _self_financing_rebalance(
                market_value,
                quality_value,
                spec.developed_market_weight,
                cost_rate,
            )
            costs.append({
                "provider_date": provider_date.date().isoformat(),
                "event": "quarterly_rebalance",
                "traded_notional_usd": one_way_notional,
                "cost_usd": rebalance_cost,
            })
        equity = market_value + quality_value
        if market_value < 0 or quality_value < 0 or equity <= 0:
            portfolio_constraint_breached = True
        records.append({
            "provider_date": provider_date,
            "strategy_equity_usd": equity,
            "benchmark_equity_usd": benchmark_value,
            "cash_equity_usd": cash_value,
        })
        previous_date = provider_date
        previous_quarter = quarter
    strategy_exit_notional = market_value + quality_value
    strategy_exit_cost = strategy_exit_notional * cost_rate
    benchmark_exit_cost = benchmark_value * cost_rate
    market_value = 0.0
    quality_value = 0.0
    strategy_ending = strategy_exit_notional - strategy_exit_cost
    benchmark_ending = benchmark_value - benchmark_exit_cost
    records[-1]["strategy_equity_usd"] = strategy_ending
    records[-1]["benchmark_equity_usd"] = benchmark_ending
    costs.append({
        "provider_date": interval.index[-1].date().isoformat(),
        "event": "final_liquidation",
        "traded_notional_usd": strategy_exit_notional,
        "cost_usd": strategy_exit_cost,
    })
    daily = pd.DataFrame(records).set_index("provider_date")
    weekly = _weekly_marks(daily, start, last_boundary, initial)
    weekly_pl = weekly["strategy_pl"]
    benchmark_pl = weekly["benchmark_pl"]
    cash_pl = weekly["cash_pl"]
    weekly_excess = weekly_pl - benchmark_pl
    lower_target, lower_excess = _bootstrap_lower_means(weekly_pl, weekly_excess, spec)
    complete_weeks = len(weekly_pl)
    mean = float(weekly_pl.mean()) if complete_weeks else None
    mean_excess = float(weekly_excess.mean()) if complete_weeks else None
    median = float(np.median(weekly_pl)) if complete_weeks else None
    profitable_fraction = float((weekly_pl > 0).mean()) if complete_weeks else None
    gross_profit = float(weekly_pl[weekly_pl > 0].sum())
    gross_loss = float(-weekly_pl[weekly_pl < 0].sum())
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else None
    profit_factor_gate = profit_factor > 1.0 if profit_factor is not None else gross_profit > 0
    weekly_rf_excess = weekly_pl - cash_pl
    deviation = float(weekly_rf_excess.std(ddof=1)) if complete_weeks > 1 else 0.0
    sharpe = (
        math.sqrt(52) * float(weekly_rf_excess.mean()) / deviation
        if deviation > 0
        else None
    )
    sharpe_gate = sharpe > 0 if sharpe is not None else float(weekly_rf_excess.mean()) > 0
    strategy_drawdown = _maximum_drawdown(
        pd.concat([pd.Series([initial]), daily["strategy_equity_usd"]], ignore_index=True)
    )
    benchmark_drawdown = _maximum_drawdown(
        pd.concat([pd.Series([initial]), daily["benchmark_equity_usd"]], ignore_index=True)
    )
    elapsed_years = (interval.index[-1].date() - start).days / 365.2425
    cagr = (strategy_ending / initial) ** (1.0 / elapsed_years) - 1.0
    gates = {
        "at least 260 complete weeks": complete_weeks >= spec.minimum_complete_weeks,
        "mean fixed-base weekly net P/L above USD 20": (
            mean is not None and mean > spec.target_weekly_profit_usd
        ),
        "one-sided 95% block-bootstrap lower mean above USD 20": (
            lower_target is not None and lower_target > spec.target_weekly_profit_usd
        ),
        "mean paired weekly excess P/L above market": mean_excess is not None and mean_excess > 0,
        "one-sided 95% paired-bootstrap lower mean excess above market": (
            lower_excess is not None and lower_excess > 0
        ),
        "positive compounded return and CAGR": strategy_ending > initial and cagr > 0,
        "ending equity above cash": strategy_ending > cash_value,
        "ending equity above after-cost market benchmark": strategy_ending > benchmark_ending,
        "maximum drawdown no worse than market benchmark": strategy_drawdown >= benchmark_drawdown,
        "weekly profit factor above one": profit_factor_gate,
        "positive median weekly P/L": median is not None and median > 0,
        "positive weekly Sharpe relative to RF": sharpe_gate,
        "more than 50% profitable weeks": (
            profitable_fraction is not None
            and profitable_fraction > spec.minimum_profitable_week_fraction
        ),
        "no leverage, shorting, or negative-equity breach": (
            not portfolio_constraint_breached
        ),
    }
    confidence_names = {
        "one-sided 95% block-bootstrap lower mean above USD 20",
        "one-sided 95% paired-bootstrap lower mean excess above market",
    }
    if complete_weeks < spec.minimum_complete_weeks:
        status = "inconclusive"
        classification_reason = f"fewer than {spec.minimum_complete_weeks} complete weeks"
    elif not all(value for name, value in gates.items() if name not in confidence_names):
        status = "fail"
        classification_reason = "one or more deterministic gates failed"
    elif not all(gates[name] for name in confidence_names):
        status = "inconclusive"
        classification_reason = "point estimates passed but confidence gates did not"
    else:
        status = "pass"
        classification_reason = "all preregistered gates passed"
    return {
        "status": status,
        "classification_reason": classification_reason,
        "date_range": {"start": start.isoformat(), "end": end.isoformat()},
        "evaluated_through": interval.index[-1].date().isoformat(),
        "starting_equity_usd": initial,
        "ending_equity_usd": strategy_ending,
        "benchmark_ending_equity_usd": benchmark_ending,
        "cash_ending_equity_usd": cash_value,
        "complete_weeks": complete_weeks,
        "weekly_pl_usd": weekly_pl.tolist(),
        "benchmark_weekly_pl_usd": benchmark_pl.tolist(),
        "weekly_excess_over_market_usd": weekly_excess.tolist(),
        "mean_weekly_net_pl_usd": mean,
        "bootstrap_95_lower_mean_weekly_pl_usd": lower_target,
        "mean_weekly_excess_over_market_usd": mean_excess,
        "bootstrap_95_lower_mean_weekly_excess_usd": lower_excess,
        "profitable_weeks_percentage": (
            100.0 * profitable_fraction if profitable_fraction is not None else None
        ),
        "median_weekly_pl_usd": median,
        "weekly_profit_factor": profit_factor,
        "weekly_sharpe_relative_to_rf": sharpe,
        "compound_annual_growth_rate": cagr,
        "maximum_drawdown": strategy_drawdown,
        "benchmark_maximum_drawdown": benchmark_drawdown,
        "total_transaction_cost_usd": float(sum(item["cost_usd"] for item in costs)),
        "cost_events": costs,
        "gates": gates,
        "failed_gates": [name for name, passed in gates.items() if not passed],
    }


def _pair_status(test_a: Mapping[str, Any], test_b: Mapping[str, Any]) -> str:
    statuses = {test_a["status"], test_b["status"]}
    if "fail" in statuses:
        return "fail"
    if "inconclusive" in statuses:
        return "inconclusive"
    return "pass"


def run_stock_quality_target_test(
    history: StockQualityHistory,
    spec: StockQualityStrategySpec | None = None,
) -> dict[str, Any]:
    """Run both locked retrospective windows through the research-result seam."""
    spec = spec or StockQualityStrategySpec()
    weights = (spec.developed_market_weight, spec.big_robust_weight)
    if any(weight < 0.0 or weight > 1.0 for weight in weights):
        raise ValueError("Stock-quality target weights permit no shorting or leverage")
    if not math.isclose(
        sum(weights), 1.0, abs_tol=1e-12
    ):
        raise ValueError("Stock-quality target weights must sum to one")
    if not 0.0 <= spec.transaction_cost_bps < 10_000.0:
        raise ValueError("Stock-quality transaction cost must be between zero and 100%")
    if spec.market_annual_drag < 0.0 or spec.big_robust_annual_drag < 0.0:
        raise ValueError("Stock-quality annual implementation drags must be nonnegative")
    frame, data_sha256 = _prepare_history(history, spec)
    test_a = _window_result(frame, spec.test_a_start, spec.test_a_end, spec)
    test_b = _window_result(frame, spec.test_b_start, spec.test_b_end, spec)
    report = {
        "research_only": True,
        "source_id": SOURCE_ID,
        "source_manifest": [dict(item) for item in history.manifest],
        "spec": spec.canonical_dict(),
        "spec_sha256": spec.sha256,
        "data_sha256": data_sha256,
        "strategy": {
            "developed_market_weight": spec.developed_market_weight,
            "big_robust_weight": spec.big_robust_weight,
            "rebalance": "quarterly",
            "leverage": 1.0,
            "shorting": False,
        },
        "test_a": test_a,
        "test_b": test_b,
        "overall_status": _pair_status(test_a, test_b),
        "warning": EVIDENCE_WARNING,
    }
    report["report_sha256"] = hashlib.sha256(_canonical_json(report).encode()).hexdigest()
    return report


def _cache_rows_sha256(rows: list[Any], manifest: list[Any]) -> str:
    material = {"source_id": SOURCE_ID, "manifest": manifest, "rows": rows}
    return hashlib.sha256(_canonical_json(material).encode()).hexdigest()


def _verify_cache(value: Any) -> StockQualityHistory:
    if not isinstance(value, dict) or value.get("source_id") != SOURCE_ID:
        raise ValueError("Stock-quality cache source identity does not match")
    rows = value.get("rows")
    manifest = value.get("manifest")
    if not isinstance(rows, list) or not isinstance(manifest, list):
        raise ValueError("Stock-quality cache rows and manifest must be lists")
    encoded_payloads = value.get("payloads_base64")
    if not isinstance(encoded_payloads, list) or len(encoded_payloads) != 2:
        raise ValueError("Stock-quality cache raw source payload coverage is incomplete")
    try:
        payloads = tuple(
            base64.b64decode(item, validate=True) for item in encoded_payloads
        )
    except (binascii.Error, TypeError, ValueError) as exc:
        raise ValueError("Stock-quality cache raw source payload is not valid base64") from exc
    expected_sources = (
        (
            "developed_five_factors_daily",
            DEVELOPED_FACTORS_DAILY_URL,
            DEVELOPED_FACTORS_DAILY_SHA256,
        ),
        (
            "developed_size_profitability_daily",
            DEVELOPED_PROFITABILITY_DAILY_URL,
            DEVELOPED_PROFITABILITY_DAILY_SHA256,
        ),
    )
    if len(manifest) != len(expected_sources):
        raise ValueError("Stock-quality cache provenance is incomplete")
    source_texts = []
    for item, payload, (role, url, pinned_sha256) in zip(
        manifest, payloads, expected_sources, strict=True
    ):
        payload_sha256 = hashlib.sha256(payload).hexdigest()
        try:
            member, text = _zip_csv_text(payload)
        except ValueError as exc:
            raise ValueError("Stock-quality cache raw source payload is invalid") from exc
        if (
            not isinstance(item, dict)
            or item.get("role") != role
            or item.get("url") != url
            or item.get("member") != member
            or item.get("returned_rows") != len(rows)
            or item.get("response_sha256") != pinned_sha256
            or payload_sha256 != pinned_sha256
        ):
            raise ValueError("Stock-quality cache provenance does not match official sources")
        source_texts.append(text)
    parsed_rows = [dict(row) for row in _aligned_source_rows(*source_texts)]
    if rows != parsed_rows:
        raise ValueError("Stock-quality cache rows do not match the raw source payload")
    expected = _cache_rows_sha256(rows, manifest)
    if value.get("rows_sha256") != expected:
        raise ValueError("Stock-quality cache row hash does not match")
    return StockQualityHistory(
        rows=tuple(rows), manifest=tuple(manifest), payloads=payloads
    )


def _atomic_private_json(path: Path, value: Any, *, pretty: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    serialized = json.dumps(
        _json_value(value),
        sort_keys=True,
        separators=None if pretty else (",", ":"),
        indent=2 if pretty else None,
        allow_nan=False,
    )
    temporary.write_text(serialized)
    temporary.chmod(0o600)
    os.replace(temporary, path)


def run_stock_quality_target_command(
    cache_path: str | Path,
    report_path: str | Path,
    *,
    source: KennethFrenchDevelopedHistory | None = None,
    spec: StockQualityStrategySpec | None = None,
) -> dict[str, Any]:
    """Load or fetch verified evidence and write a deterministic private report."""
    spec = spec or StockQualityStrategySpec()
    cache_path = Path(cache_path)
    report_path = Path(report_path)
    write_cache = False
    if cache_path.exists():
        history = _verify_cache(json.loads(cache_path.read_text()))
        cache_path.chmod(0o600)
    else:
        provider = source or KennethFrenchDevelopedHistory()
        fetched = provider.fetch()
        rows = [dict(row) for row in fetched.rows]
        manifest = [dict(item) for item in fetched.manifest]
        cached = {
            "source_id": SOURCE_ID,
            "rows": rows,
            "manifest": manifest,
            "payloads_base64": [
                base64.b64encode(payload).decode("ascii") for payload in fetched.payloads
            ],
            "rows_sha256": _cache_rows_sha256(rows, manifest),
        }
        history = _verify_cache(cached)
        write_cache = True
    report = run_stock_quality_target_test(history, spec)
    if write_cache:
        _atomic_private_json(cache_path, cached, pretty=False)
    _atomic_private_json(report_path, report, pretty=True)
    report_path.chmod(0o600)
    return report
