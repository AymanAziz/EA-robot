"""Research-only XAU/USD weekly-profit target evaluation.

The module is deliberately isolated from operational instruments, persistence,
the trading engine, and every order adapter.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import time
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from types import MappingProxyType
from typing import Any, Mapping
from pathlib import Path

import httpx
import numpy as np
import pandas as pd


SOURCE_ID = "algospecial_xauusd_d1_preview"
ALGOSPECIAL_OHLC_URL = "https://www.algospecial.com/api/ohlc.php"
PROVIDER_CLOCK = "broker server time; timezone unknown"
EVIDENCE_WARNING = (
    "Historical research from an unidentified Exness-style MT5 feed; not OANDA, "
    "not a broker paper fill, and not evidence of future weekly profit."
)


def _canonical_json(value: Any) -> str:
    return json.dumps(_json_value(value), sort_keys=True, separators=(",", ":"), allow_nan=False)


def _json_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_value(item) for item in value]
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float):
        if np.isnan(value):
            return None
        if not np.isfinite(value):
            raise ValueError("Canonical weekly evidence cannot contain infinity")
    return value


@dataclass(frozen=True)
class DailyGoldHistory:
    rows: tuple[Mapping[str, Any], ...]
    manifest: tuple[Mapping[str, Any], ...]

    def __post_init__(self):
        object.__setattr__(self, "rows", tuple(MappingProxyType(dict(row)) for row in self.rows))
        object.__setattr__(self, "manifest", tuple(
            MappingProxyType(dict(item)) for item in self.manifest
        ))


@dataclass(frozen=True)
class PreparedDailyGoldHistory:
    frame: pd.DataFrame
    manifest: tuple[Mapping[str, Any], ...]
    data_sha256: str
    source_id: str = SOURCE_ID


def _prepared_data_sha256(
    frame: pd.DataFrame, manifest: tuple[Mapping[str, Any], ...]
) -> str:
    records = frame.reset_index().copy()
    records["provider_time"] = records["provider_time"].dt.strftime("%Y-%m-%dT%H:%M:%S")
    material = {
        "source_id": SOURCE_ID,
        "manifest": tuple(dict(item) for item in manifest),
        "rows": records.to_dict("records"),
    }
    return hashlib.sha256(_canonical_json(material).encode()).hexdigest()


def prepare_daily_gold_history(history: DailyGoldHistory) -> PreparedDailyGoldHistory:
    """Validate D1 rows without inventing a timezone for the provider clock."""
    frame = pd.DataFrame(history.rows).rename(columns={
        "Open": "open",
        "High": "high",
        "Low": "low",
        "Close": "close",
        "TickVolume": "volume",
        "Spread": "spread_points",
    })
    required = {"Timestamp", "open", "high", "low", "close", "volume", "spread_points"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"Daily gold history is missing required fields: {sorted(missing)}")
    provider_time = pd.to_datetime(
        frame.pop("Timestamp"), format="%Y.%m.%d %H:%M:%S", errors="raise"
    )
    frame.index = pd.DatetimeIndex(provider_time, name="provider_time")
    if frame.empty:
        raise ValueError("Daily gold history contains no rows")
    if not frame.index.is_unique or not frame.index.is_monotonic_increasing:
        raise ValueError("Daily provider times must be unique and strictly increasing")
    if frame.index.to_series().diff().gt(pd.to_timedelta(7, unit="D")).any():
        raise ValueError("Daily gold history contains a gap greater than seven calendar days")
    price_columns = ["open", "high", "low", "close"]
    frame[price_columns] = frame[price_columns].astype(float)
    prices = frame[price_columns].to_numpy()
    if not np.isfinite(prices).all() or (prices <= 0).any():
        raise ValueError("Daily gold history requires finite positive prices")
    invalid_ohlc = (
        frame["high"].lt(frame[price_columns].max(axis=1))
        | frame["low"].gt(frame[price_columns].min(axis=1))
    )
    if invalid_ohlc.any():
        raise ValueError("Daily gold history violates OHLC invariants")
    frame["volume"] = pd.to_numeric(frame["volume"], errors="raise")
    if not np.isfinite(frame["volume"]).all() or frame["volume"].lt(0).any():
        raise ValueError("Daily gold history requires finite nonnegative tick volume")
    frame["spread_points"] = pd.to_numeric(frame["spread_points"], errors="raise")
    observed_spread = frame["spread_points"].dropna()
    if not np.isfinite(observed_spread).all() or observed_spread.lt(0).any():
        raise ValueError("Daily gold history requires finite nonnegative spread points when observed")
    frame["spread_usd"] = frame["spread_points"].astype(float) * 0.001
    digest = _prepared_data_sha256(frame, history.manifest)
    return PreparedDailyGoldHistory(
        frame=frame.copy(deep=True), manifest=history.manifest, data_sha256=digest
    )


class AlgoSpecialGoldDailyHistory:
    """Bounded client for the provider's keyless D1 preview endpoint."""

    def __init__(self, client: httpx.Client | None = None, sleeper=time.sleep):
        self._client = client or httpx.Client(timeout=30)
        self._sleeper = sleeper

    def fetch(self, start: date, end: date) -> DailyGoldHistory:
        if end < start:
            raise ValueError("Daily gold history end date must not precede start date")
        rows: list[Mapping[str, Any]] = []
        manifest: list[Mapping[str, Any]] = []
        cursor = start
        while cursor <= end:
            chunk_end = min(cursor + timedelta(days=30), end)
            params = {
                "symbol": "XAUUSD",
                "tf": "D1",
                "from": cursor.isoformat(),
                "to": chunk_end.isoformat(),
                "format": "json",
            }
            response = self._client.get(ALGOSPECIAL_OHLC_URL, params=params)
            if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", "60"))
                self._sleeper(retry_after)
                response = self._client.get(ALGOSPECIAL_OHLC_URL, params=params)
            response.raise_for_status()
            payload = response.json()
            chunk_rows = payload.get("data")
            if not isinstance(chunk_rows, list):
                raise ValueError("AlgoSpecial D1 response data must be a list")
            expected = {
                "symbol": "XAUUSD",
                "timeframe": "D1",
                "from": cursor.isoformat(),
                "to": chunk_end.isoformat(),
            }
            if any(payload.get(key) != value for key, value in expected.items()) or (
                payload.get("rows") != len(chunk_rows)
            ):
                raise ValueError("AlgoSpecial D1 metadata does not match the request or rows")
            try:
                row_dates = [
                    datetime.strptime(row["Timestamp"], "%Y.%m.%d %H:%M:%S").date()
                    for row in chunk_rows
                ]
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError("AlgoSpecial D1 response contains an invalid timestamp") from exc
            if any(stamp < cursor or stamp > chunk_end for stamp in row_dates):
                raise ValueError("AlgoSpecial D1 row lies outside its requested chunk")
            core_payload = {**expected, "rows": len(chunk_rows), "data": chunk_rows}
            rows.extend(dict(row) for row in chunk_rows)
            manifest.append({
                "endpoint": ALGOSPECIAL_OHLC_URL,
                "request_start": cursor.isoformat(),
                "request_end": chunk_end.isoformat(),
                "symbol": "XAUUSD",
                "timeframe": "D1",
                "provider_clock": PROVIDER_CLOCK,
                "returned_rows": len(chunk_rows),
                "chunk_sha256": hashlib.sha256(_canonical_json(core_payload).encode()).hexdigest(),
            })
            cursor = chunk_end + timedelta(days=1)
        return DailyGoldHistory(rows=tuple(rows), manifest=tuple(manifest))


@dataclass(frozen=True)
class GoldWeeklyStrategySpec:
    """Immutable preregistration for the single weekly-target hypothesis."""

    strategy_version: str = "gold_weekly_tsm_v1"
    timeframe: str = "D1"
    execution_timing: str = "completed month signal; first next-month D1 open"
    momentum_sign_rule: str = "strictly positive=+1; nonpositive=-1; mean 1/3/12-month signs"
    quantity_rounding: str = "toward zero to six research-ounce decimals"
    weekly_block_rule: str = "consecutive seven-day blocks anchored at each test start"
    bootstrap_rule: str = "circular blocks; floor(sqrt(weeks)); 10000 samples; seed 42"
    bootstrap_quantile: float = 0.05
    spread_rule: str = "one full observed spread per transaction; warm-up nonzero p99 fallback"
    financing_rule: str = "absolute prior-close notional times annual rate times calendar days/365"
    benchmark_rule: str = "same-cost unleveraged buy-and-hold with daily financing"
    mark_rule: str = "immediate adverse liquidation including spread, slippage, and commission"
    account_margin_rule: str = (
        "broker account margin unavailable; research-only; not evaluated as a pass gate"
    )
    initial_equity_usd: float = 10_000.0
    momentum_months: tuple[int, ...] = (1, 3, 12)
    volatility_months: int = 12
    annual_volatility_target: float = 0.10
    maximum_notional_multiple: float = 1.0
    target_weekly_profit_usd: float = 20.0
    minimum_complete_weeks: int = 52
    slippage_bps_per_side: float = 2.0
    commission_bps_per_side: float = 1.0
    spread_point_value_usd: float = 0.001
    financing_rates: tuple[float, ...] = (0.05, 0.10, 0.15)
    primary_financing_rate: float = 0.10
    source_start: date = date(2020, 12, 1)
    source_end: date = date(2023, 12, 31)
    test_a_start: date = date(2022, 1, 1)
    test_a_end: date = date(2022, 12, 31)
    test_b_start: date = date(2023, 1, 1)
    test_b_end: date = date(2023, 12, 31)
    bootstrap_samples: int = 10_000
    bootstrap_seed: int = 42
    maximum_drawdown: float = 0.10

    def canonical_dict(self) -> dict[str, Any]:
        values = asdict(self)
        return {
            key: value.isoformat() if isinstance(value, date) else value
            for key, value in values.items()
        }

    @property
    def sha256(self) -> str:
        encoded = json.dumps(
            self.canonical_dict(), sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
        return hashlib.sha256(encoded).hexdigest()


def _spread_or_fallback(value: Any, fallback: float) -> float:
    spread = float(value) if value is not None and pd.notna(value) else 0.0
    return spread if spread > 0 else fallback


def _monthly_exposure(frame: pd.DataFrame, spec: GoldWeeklyStrategySpec) -> pd.Series:
    monthly_close = frame["close"].groupby(frame.index.to_period("M")).last()
    expected_months = pd.period_range(
        monthly_close.index.min(), monthly_close.index.max(), freq="M"
    )
    if not monthly_close.index.equals(expected_months):
        raise ValueError("Weekly gold history requires complete consecutive provider months")
    monthly_returns = monthly_close.pct_change(fill_method=None)
    signs = []
    for months in spec.momentum_months:
        momentum = monthly_close.pct_change(months, fill_method=None)
        signs.append(pd.Series(np.where(momentum > 0, 1.0, -1.0), index=momentum.index).where(
            momentum.notna()
        ))
    score = pd.concat(signs, axis=1).mean(axis=1, skipna=False)
    volatility = (
        monthly_returns.rolling(spec.volatility_months).std(ddof=1) * math.sqrt(12)
    )
    multiplier = (spec.annual_volatility_target / volatility).clip(upper=1.0)
    exposure = score * multiplier
    return exposure.where(np.isfinite(exposure)).dropna()


def _round_toward_zero(value: float, decimals: int = 6) -> float:
    scale = 10 ** decimals
    return math.trunc(value * scale) / scale


def _liquidation_equity(
    cash: float,
    quantity: float,
    price: float,
    spread: float,
    spec: GoldWeeklyStrategySpec,
) -> float:
    if quantity == 0:
        return cash
    slippage = spec.slippage_bps_per_side / 10_000
    commission = spec.commission_bps_per_side / 10_000
    if quantity > 0:
        fill = price - spread - price * slippage
        return cash + quantity * fill - quantity * fill * commission
    fill = price + spread + price * slippage
    units = abs(quantity)
    return cash - units * fill - units * fill * commission


def _execute_delta(
    *,
    cash: float,
    quantity: float,
    delta: float,
    price: float,
    spread: float,
    provider_time: pd.Timestamp,
    event: str,
    spec: GoldWeeklyStrategySpec,
) -> tuple[float, float, dict[str, Any]]:
    slippage = spec.slippage_bps_per_side / 10_000
    commission_rate = spec.commission_bps_per_side / 10_000
    if delta > 0:
        side = "buy"
        fill = price + spread + price * slippage
        gross = delta * fill
        commission = gross * commission_rate
        cash -= gross + commission
    elif delta < 0:
        side = "sell"
        fill = price - spread - price * slippage
        gross = abs(delta) * fill
        commission = gross * commission_rate
        cash += gross - commission
    else:
        raise ValueError("A weekly gold transaction requires nonzero quantity")
    quantity += delta
    transaction = {
        "provider_time": provider_time.isoformat(),
        "event": event,
        "side": side,
        "quantity_ounces": abs(delta),
        "source_price": price,
        "spread_usd": spread,
        "slippage_usd_per_ounce": price * slippage,
        "fill_price": fill,
        "commission_usd": commission,
        "position_after_ounces": quantity,
    }
    return cash, quantity, transaction


def _rebalance(
    *,
    cash: float,
    quantity: float,
    target_quantity: float,
    price: float,
    spread: float,
    provider_time: pd.Timestamp,
    spec: GoldWeeklyStrategySpec,
    transactions: list[dict[str, Any]],
) -> tuple[float, float]:
    if math.isclose(quantity, target_quantity, abs_tol=1e-12):
        return cash, quantity
    if quantity and target_quantity and quantity * target_quantity < 0:
        cash, quantity, closed = _execute_delta(
            cash=cash, quantity=quantity, delta=-quantity, price=price, spread=spread,
            provider_time=provider_time, event="direction_close", spec=spec,
        )
        transactions.append(closed)
        cash, quantity, opened = _execute_delta(
            cash=cash, quantity=quantity, delta=target_quantity, price=price, spread=spread,
            provider_time=provider_time, event="direction_open", spec=spec,
        )
        transactions.append(opened)
        return cash, quantity
    cash, quantity, transaction = _execute_delta(
        cash=cash, quantity=quantity, delta=target_quantity - quantity,
        price=price, spread=spread, provider_time=provider_time,
        event="rebalance", spec=spec,
    )
    transactions.append(transaction)
    return cash, quantity


def _bootstrap_lower_mean(values: np.ndarray, spec: GoldWeeklyStrategySpec) -> float | None:
    count = len(values)
    if count < 2:
        return None
    block_length = max(2, int(math.sqrt(count)))
    blocks_needed = math.ceil(count / block_length)
    generator = np.random.default_rng(spec.bootstrap_seed)
    starts = generator.integers(0, count, size=(spec.bootstrap_samples, blocks_needed))
    offsets = np.arange(block_length)
    indices = (starts[..., None] + offsets) % count
    samples = values[indices.reshape(spec.bootstrap_samples, -1)[:, :count]]
    return float(np.quantile(samples.mean(axis=1), spec.bootstrap_quantile))


def classify_weekly_target_evidence(
    weekly_pl_usd: list[float] | tuple[float, ...] | np.ndarray,
    *,
    maximum_drawdown: float,
    buy_hold_net_pl_usd: float,
    notional_cap_breached: bool,
    spec: GoldWeeklyStrategySpec | None = None,
) -> dict[str, Any]:
    """Classify known weekly outcomes under the frozen USD 20 evidence contract."""
    spec = spec or GoldWeeklyStrategySpec()
    weekly = np.asarray(weekly_pl_usd, dtype=float)
    if not np.isfinite(weekly).all():
        raise ValueError("Weekly P/L evidence must contain only finite values")
    complete_weeks = len(weekly)
    mean = float(weekly.mean()) if complete_weeks else None
    lower = _bootstrap_lower_mean(weekly, spec)
    median = float(np.median(weekly)) if complete_weeks else None
    gross_profit = float(weekly[weekly > 0].sum())
    gross_loss = float(-weekly[weekly < 0].sum())
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else None
    profit_factor_gate = profit_factor > 1 if profit_factor is not None else gross_profit > 0
    deviation = float(weekly.std(ddof=1)) if complete_weeks > 1 else 0.0
    sharpe = math.sqrt(52) * mean / deviation if deviation > 0 and mean is not None else None
    total = float(weekly.sum())
    required_total = spec.target_weekly_profit_usd * complete_weeks
    gates = {
        "at least 52 complete weeks": complete_weeks >= spec.minimum_complete_weeks,
        "mean weekly net P/L above USD 20": mean is not None and mean > spec.target_weekly_profit_usd,
        "one-sided 95% bootstrap lower mean above USD 20": (
            lower is not None and lower > spec.target_weekly_profit_usd
        ),
        "positive total after-cost P/L": total > 0,
        "total net P/L above USD 20 per complete week": total > required_total,
        "weekly profit factor above one": profit_factor_gate,
        "maximum drawdown no worse than -10%": maximum_drawdown >= -spec.maximum_drawdown,
        "positive weekly Sharpe": sharpe is not None and sharpe > 0,
        "positive median weekly P/L": median is not None and median > 0,
        "no notional cap breach": not notional_cap_breached,
        "outperform cash": total > 0,
        "outperform same-cost buy-and-hold": total > buy_hold_net_pl_usd,
    }
    if complete_weeks < spec.minimum_complete_weeks:
        status = "inconclusive"
    elif not gates["mean weekly net P/L above USD 20"]:
        status = "fail"
    else:
        non_confidence = [
            value for name, value in gates.items()
            if name != "one-sided 95% bootstrap lower mean above USD 20"
        ]
        if not all(non_confidence):
            status = "fail"
        elif not gates["one-sided 95% bootstrap lower mean above USD 20"]:
            status = "inconclusive"
        else:
            status = "pass"
    weeks_above_target = int((weekly > spec.target_weekly_profit_usd).sum())
    profitable_weeks = int((weekly > 0).sum())
    return {
        "status": status,
        "complete_weeks": complete_weeks,
        "mean_weekly_net_pl_usd": mean,
        "bootstrap_95_lower_mean_weekly_pl_usd": lower,
        "total_net_pl_usd": total,
        "required_total_net_pl_usd": required_total,
        "weekly_profit_factor": profit_factor,
        "weekly_sharpe": sharpe,
        "maximum_drawdown": float(maximum_drawdown),
        "median_weekly_pl_usd": median,
        "fifth_percentile_weekly_pl_usd": (
            float(np.quantile(weekly, 0.05)) if complete_weeks else None
        ),
        "worst_weekly_pl_usd": float(weekly.min()) if complete_weeks else None,
        "weeks_above_usd_20": weeks_above_target,
        "weeks_above_usd_20_percentage": (
            100 * weeks_above_target / complete_weeks if complete_weeks else None
        ),
        "profitable_weeks": profitable_weeks,
        "profitable_weeks_percentage": (
            100 * profitable_weeks / complete_weeks if complete_weeks else None
        ),
        "weekly_pl_usd": weekly.tolist(),
        "buy_hold_net_pl_usd": float(buy_hold_net_pl_usd),
        "notional_cap_breached": bool(notional_cap_breached),
        "gates": gates,
    }


def classify_weekly_target_pair(
    test_a: Mapping[str, Any], test_b: Mapping[str, Any]
) -> str:
    """Apply fail-first then inconclusive precedence to two holdout classifications."""
    statuses = (test_a["status"], test_b["status"])
    if "fail" in statuses:
        return "fail"
    if "inconclusive" in statuses:
        return "inconclusive"
    if statuses != ("pass", "pass"):
        raise ValueError("Weekly target status must be pass, fail, or inconclusive")
    return "pass"


def _frame_sha256(frame: pd.DataFrame) -> str:
    records = frame.reset_index().copy()
    records["provider_time"] = records["provider_time"].dt.strftime("%Y-%m-%dT%H:%M:%S")
    return hashlib.sha256(_canonical_json(records.to_dict("records")).encode()).hexdigest()


def _weekly_boundaries(start: date, end: date) -> list[pd.Timestamp]:
    complete = ((end - start).days + 1) // 7
    return [
        pd.Timestamp(start) + pd.to_timedelta(7 * index, unit="D")
        for index in range(complete + 1)
    ]


def _mark_snapshot_at_boundary(
    snapshots: list[dict[str, Any]],
    boundary: pd.Timestamp,
    initial_equity: float,
    financing_rate: float,
    fallback: float,
    spec: GoldWeeklyStrategySpec,
) -> float:
    eligible = [item for item in snapshots if item["provider_time"] < boundary]
    if not eligible:
        return initial_equity
    snapshot = eligible[-1]
    days = max((boundary - snapshot["provider_time"]).total_seconds() / 86_400, 0.0)
    cash = snapshot["cash"] - (
        abs(snapshot["quantity"] * snapshot["close"]) * financing_rate * days / 365
    )
    spread = _spread_or_fallback(snapshot["spread_usd"], fallback)
    return _liquidation_equity(
        cash, snapshot["quantity"], snapshot["close"], spread, spec
    )


def _simulate_test(
    frame: pd.DataFrame,
    exposures: pd.Series,
    *,
    start: date,
    end: date,
    financing_rate: float,
    fallback: float,
    spec: GoldWeeklyStrategySpec,
) -> dict[str, Any]:
    boundaries = _weekly_boundaries(start, end)
    final_boundary = boundaries[-1]
    interval = frame[(frame.index >= pd.Timestamp(start)) & (frame.index < final_boundary)]
    if interval.empty:
        raise ValueError("Weekly gold test interval contains no completed D1 rows")
    cash = spec.initial_equity_usd
    quantity = 0.0
    transactions: list[dict[str, Any]] = []
    snapshots: list[dict[str, Any]] = []
    maximum_notional = 0.0
    prior_time: pd.Timestamp | None = None
    prior_close: float | None = None
    prior_period = None
    cap_breach = False
    for provider_time, row in interval.iterrows():
        if prior_time is not None and prior_close is not None:
            days = max((provider_time - prior_time).total_seconds() / 86_400, 0.0)
            cash -= abs(quantity * prior_close) * financing_rate * days / 365
        current_period = provider_time.to_period("M")
        if current_period != prior_period:
            signal_period = current_period - 1
            if signal_period not in exposures.index:
                raise ValueError(f"Missing frozen monthly exposure for {signal_period}")
            open_price = float(row["open"])
            spread = _spread_or_fallback(row["spread_usd"], fallback)
            target_fraction = float(np.clip(
                exposures.loc[signal_period],
                -spec.maximum_notional_multiple,
                spec.maximum_notional_multiple,
            ))
            target_notional = target_fraction * spec.initial_equity_usd
            target_quantity = _round_toward_zero(target_notional / open_price)
            raw_notional = abs(target_quantity * open_price)
            fixed_cap = spec.initial_equity_usd * spec.maximum_notional_multiple
            cap_breach = cap_breach or raw_notional > fixed_cap + 0.01
            maximum_notional = max(maximum_notional, raw_notional)
            cash, quantity = _rebalance(
                cash=cash, quantity=quantity, target_quantity=target_quantity,
                price=open_price, spread=spread, provider_time=provider_time,
                spec=spec, transactions=transactions,
            )
            post_trade_equity = _liquidation_equity(
                cash, quantity, open_price, spread, spec
            )
            post_trade_notional = abs(quantity * open_price)
            cap_breach = cap_breach or post_trade_equity <= 0 or (
                post_trade_notional
                > post_trade_equity * spec.maximum_notional_multiple + 0.01
            )
        close = float(row["close"])
        spread = _spread_or_fallback(row["spread_usd"], fallback)
        close_notional = abs(quantity * close)
        maximum_notional = max(maximum_notional, close_notional)
        cap_breach = cap_breach or close_notional > (
            spec.initial_equity_usd * spec.maximum_notional_multiple + 0.01
        )
        equity = _liquidation_equity(cash, quantity, close, spread, spec)
        snapshots.append({
            "provider_time": provider_time,
            "cash": cash,
            "quantity": quantity,
            "close": close,
            "spread_usd": row["spread_usd"],
            "equity": equity,
        })
        prior_time, prior_close, prior_period = provider_time, close, current_period

    last = snapshots[-1]
    cash = last["cash"]
    quantity = last["quantity"]
    if quantity:
        spread = _spread_or_fallback(last["spread_usd"], fallback)
        cash, quantity = _rebalance(
            cash=cash, quantity=quantity, target_quantity=0.0,
            price=last["close"], spread=spread,
            provider_time=last["provider_time"], spec=spec,
            transactions=transactions,
        )
        transactions[-1]["event"] = "forced_boundary_exit"
    boundary_equity = [
        _mark_snapshot_at_boundary(
            snapshots, boundary, spec.initial_equity_usd, financing_rate, fallback, spec
        )
        for boundary in boundaries[:-1]
    ] + [cash]
    weekly_pl = np.diff(np.asarray(boundary_equity, dtype=float))
    provider_equity = np.asarray(
        [spec.initial_equity_usd] + [float(item["equity"]) for item in snapshots] + [cash]
    )
    return {
        "starting_equity_usd": spec.initial_equity_usd,
        "final_equity_usd": cash,
        "weekly_pl": weekly_pl,
        "boundary_equity": boundary_equity,
        "provider_equity": provider_equity,
        "transactions": transactions,
        "maximum_absolute_notional_usd": maximum_notional,
        "notional_cap_breached": cap_breach,
        "partition_sha256": _frame_sha256(interval),
        "start": start.isoformat(),
        "end": end.isoformat(),
        "complete_block_boundary": final_boundary.date().isoformat(),
        "final_exit_provider_time": last["provider_time"].isoformat(),
        "financing_stopped_at_provider_time": last["provider_time"].isoformat(),
    }


def _simulate_buy_hold(
    frame: pd.DataFrame,
    *,
    start: date,
    end: date,
    financing_rate: float,
    fallback: float,
    spec: GoldWeeklyStrategySpec,
) -> dict[str, Any]:
    boundaries = _weekly_boundaries(start, end)
    final_boundary = boundaries[-1]
    interval = frame[(frame.index >= pd.Timestamp(start)) & (frame.index < final_boundary)]
    first, last = interval.iloc[0], interval.iloc[-1]
    entry_price = float(first["open"])
    entry_spread = _spread_or_fallback(first["spread_usd"], fallback)
    slippage = spec.slippage_bps_per_side / 10_000
    commission = spec.commission_bps_per_side / 10_000
    entry_fill = entry_price + entry_spread + entry_price * slippage
    quantity = spec.initial_equity_usd / (entry_fill * (1 + commission))
    cash = spec.initial_equity_usd - quantity * entry_fill * (1 + commission)
    prior_time = interval.index[0]
    prior_close = float(first["close"])
    for provider_time, row in interval.iloc[1:].iterrows():
        days = max((provider_time - prior_time).total_seconds() / 86_400, 0.0)
        cash -= abs(quantity * prior_close) * financing_rate * days / 365
        prior_time, prior_close = provider_time, float(row["close"])
    exit_price = float(last["close"])
    exit_spread = _spread_or_fallback(last["spread_usd"], fallback)
    exit_fill = exit_price - exit_spread - exit_price * slippage
    cash += quantity * exit_fill * (1 - commission)
    final_exit_provider_time = interval.index[-1].isoformat()
    return {
        "net_pl_usd": cash - spec.initial_equity_usd,
        "final_exit_provider_time": final_exit_provider_time,
        "financing_stopped_at_provider_time": final_exit_provider_time,
    }


def _summarize_test(
    replay: Mapping[str, Any], benchmark: Mapping[str, Any], spec: GoldWeeklyStrategySpec
) -> dict[str, Any]:
    weekly = np.asarray(replay["weekly_pl"], dtype=float)
    provider_equity = np.asarray(replay["provider_equity"], dtype=float)
    peaks = np.maximum.accumulate(provider_equity)
    drawdowns = np.divide(
        provider_equity - peaks, peaks, out=np.zeros_like(provider_equity), where=peaks != 0
    )
    max_drawdown = float(drawdowns.min())
    classification = classify_weekly_target_evidence(
        weekly,
        maximum_drawdown=max_drawdown,
        buy_hold_net_pl_usd=benchmark["net_pl_usd"],
        notional_cap_breached=replay["notional_cap_breached"],
        spec=spec,
    )
    complete_block_boundary = date.fromisoformat(replay["complete_block_boundary"])
    end = date.fromisoformat(replay["end"])
    excluded_days = max((end - complete_block_boundary).days + 1, 0)
    return {
        **classification,
        "starting_equity_usd": replay["starting_equity_usd"],
        "final_equity_usd": replay["final_equity_usd"],
        "maximum_absolute_notional_usd": replay["maximum_absolute_notional_usd"],
        "transactions": tuple(dict(item) for item in replay["transactions"]),
        "partition_sha256": replay["partition_sha256"],
        "final_exit_provider_time": replay["final_exit_provider_time"],
        "financing_stopped_at_provider_time": replay["financing_stopped_at_provider_time"],
        "buy_hold_final_exit_provider_time": benchmark["final_exit_provider_time"],
        "buy_hold_financing_stopped_at_provider_time": (
            benchmark["financing_stopped_at_provider_time"]
        ),
        "excluded_incomplete_final_block": {
            "days": excluded_days,
            "start_provider_date": (
                complete_block_boundary.isoformat() if excluded_days else None
            ),
            "end_provider_date": end.isoformat() if excluded_days else None,
        },
    }


def run_gold_weekly_target_test(
    prepared: PreparedDailyGoldHistory,
    spec: GoldWeeklyStrategySpec | None = None,
) -> dict[str, Any]:
    """Evaluate one frozen TSM rule on two separate chronological holdouts."""
    spec = spec or GoldWeeklyStrategySpec()
    frame = prepared.frame
    if _prepared_data_sha256(frame, prepared.manifest) != prepared.data_sha256:
        raise ValueError("Prepared daily gold history changed after preparation")
    if frame.index[0].date() > spec.source_start or frame.index[-1].date() < spec.source_end - timedelta(days=7):
        raise ValueError("Daily gold history does not cover the locked source interval")
    exposures = _monthly_exposure(frame, spec)
    development_spreads = frame.loc[frame.index < pd.Timestamp(spec.test_a_start), "spread_usd"]
    development_spreads = development_spreads[
        development_spreads.gt(0) & np.isfinite(development_spreads)
    ]
    if development_spreads.empty:
        raise ValueError("Warm-up data requires a nonzero spread for the frozen fallback")
    fallback = float(np.quantile(development_spreads, 0.99, method="higher"))
    sensitivities: dict[str, Any] = {}
    primary_a = primary_b = None
    for rate in spec.financing_rates:
        replay_a = _simulate_test(
            frame, exposures, start=spec.test_a_start, end=spec.test_a_end,
            financing_rate=rate, fallback=fallback, spec=spec,
        )
        replay_b = _simulate_test(
            frame, exposures, start=spec.test_b_start, end=spec.test_b_end,
            financing_rate=rate, fallback=fallback, spec=spec,
        )
        benchmark_a = _simulate_buy_hold(
            frame, start=spec.test_a_start, end=spec.test_a_end,
            financing_rate=rate, fallback=fallback, spec=spec,
        )
        benchmark_b = _simulate_buy_hold(
            frame, start=spec.test_b_start, end=spec.test_b_end,
            financing_rate=rate, fallback=fallback, spec=spec,
        )
        summary_a = _summarize_test(replay_a, benchmark_a, spec)
        summary_b = _summarize_test(replay_b, benchmark_b, spec)
        key = f"{rate:.2f}"
        sensitivities[key] = {
            "annual_financing_rate": rate,
            "test_a": summary_a,
            "test_b": summary_b,
            "overall_status": classify_weekly_target_pair(summary_a, summary_b),
        }
        if math.isclose(rate, spec.primary_financing_rate):
            primary_a, primary_b = summary_a, summary_b
    if primary_a is None or primary_b is None:
        raise ValueError("Primary financing rate must be one of the frozen sensitivities")
    report = {
        "source_id": SOURCE_ID,
        "warning": EVIDENCE_WARNING,
        "provider_time": PROVIDER_CLOCK,
        "spec": spec.canonical_dict(),
        "spec_sha256": spec.sha256,
        "data_sha256": prepared.data_sha256,
        "manifest": tuple(dict(item) for item in prepared.manifest),
        "strategy": "fixed 1/3/12-month time-series momentum with volatility targeting",
        "development_spread_p99_usd": fallback,
        "primary_financing_rate": spec.primary_financing_rate,
        "account_margin_evidence": {
            "status": "unavailable",
            "classification": "research-only; not evaluated as a pass gate",
        },
        "test_a": primary_a,
        "test_b": primary_b,
        "financing_sensitivities": sensitivities,
        "overall_status": classify_weekly_target_pair(primary_a, primary_b),
    }
    report["report_sha256"] = hashlib.sha256(_canonical_json(report).encode()).hexdigest()
    return report


def _expected_chunks(start: date, end: date) -> list[tuple[date, date]]:
    chunks = []
    cursor = start
    while cursor <= end:
        chunk_end = min(cursor + timedelta(days=30), end)
        chunks.append((cursor, chunk_end))
        cursor = chunk_end + timedelta(days=1)
    return chunks


def _verify_daily_cache(cached: Mapping[str, Any], spec: GoldWeeklyStrategySpec) -> DailyGoldHistory:
    identity = (
        cached.get("source_id"), cached.get("timeframe"),
        cached.get("start"), cached.get("end"),
    )
    expected_identity = (
        SOURCE_ID, "D1", spec.source_start.isoformat(), spec.source_end.isoformat(),
    )
    if identity != expected_identity:
        raise ValueError("Weekly gold cache identity or locked date range does not match")
    rows = cached.get("rows")
    manifest = cached.get("manifest")
    chunks = _expected_chunks(spec.source_start, spec.source_end)
    if not isinstance(rows, list) or not isinstance(manifest, list) or len(manifest) != len(chunks):
        raise ValueError("Weekly gold cache manifest coverage is incomplete")
    offset = 0
    for item, (chunk_start, chunk_end) in zip(manifest, chunks, strict=True):
        expected = {
            "endpoint": ALGOSPECIAL_OHLC_URL,
            "request_start": chunk_start.isoformat(),
            "request_end": chunk_end.isoformat(),
            "symbol": "XAUUSD",
            "timeframe": "D1",
            "provider_clock": PROVIDER_CLOCK,
        }
        returned = item.get("returned_rows") if isinstance(item, Mapping) else None
        if (
            not isinstance(item, Mapping)
            or any(item.get(key) != value for key, value in expected.items())
            or not isinstance(returned, int)
            or returned < 0
        ):
            raise ValueError("Weekly gold cache manifest entry is invalid")
        chunk_rows = rows[offset:offset + returned]
        try:
            row_dates = [
                datetime.strptime(row["Timestamp"], "%Y.%m.%d %H:%M:%S").date()
                for row in chunk_rows
            ]
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("Weekly gold cache row timestamp is invalid") from exc
        if any(stamp < chunk_start or stamp > chunk_end for stamp in row_dates):
            raise ValueError("Weekly gold cache row lies outside its manifest chunk")
        core = {
            "symbol": "XAUUSD",
            "timeframe": "D1",
            "from": chunk_start.isoformat(),
            "to": chunk_end.isoformat(),
            "rows": returned,
            "data": chunk_rows,
        }
        digest = hashlib.sha256(_canonical_json(core).encode()).hexdigest()
        if len(chunk_rows) != returned or item.get("chunk_sha256") != digest:
            raise ValueError("Weekly gold cache chunk hash does not match its manifest")
        offset += returned
    if offset != len(rows):
        raise ValueError("Weekly gold cache has rows outside its manifest")
    return DailyGoldHistory(rows=tuple(rows), manifest=tuple(manifest))


def _atomic_private_json(path: Path, value: Any, *, pretty: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    serialized = json.dumps(
        _json_value(value), sort_keys=True,
        separators=None if pretty else (",", ":"),
        indent=2 if pretty else None,
        allow_nan=False,
    )
    temporary.write_text(serialized)
    temporary.chmod(0o600)
    os.replace(temporary, path)


def run_gold_weekly_target_command(
    cache_path: str | Path,
    report_path: str | Path,
    *,
    source: AlgoSpecialGoldDailyHistory | None = None,
    spec: GoldWeeklyStrategySpec | None = None,
) -> dict[str, Any]:
    """Load or fetch the locked D1 evidence, then write a deterministic private report."""
    spec = spec or GoldWeeklyStrategySpec()
    cache_path = Path(cache_path)
    report_path = Path(report_path)
    write_cache = False
    if cache_path.exists():
        cached = json.loads(cache_path.read_text())
        history = _verify_daily_cache(cached, spec)
        cache_path.chmod(0o600)
    else:
        provider = source or AlgoSpecialGoldDailyHistory()
        fetched = provider.fetch(spec.source_start, spec.source_end)
        cached = {
            "source_id": SOURCE_ID,
            "timeframe": "D1",
            "start": spec.source_start.isoformat(),
            "end": spec.source_end.isoformat(),
            "rows": [dict(row) for row in fetched.rows],
            "manifest": [dict(item) for item in fetched.manifest],
        }
        history = _verify_daily_cache(cached, spec)
        write_cache = True
    prepared = prepare_daily_gold_history(history)
    if write_cache:
        _atomic_private_json(cache_path, cached, pretty=False)
    report = run_gold_weekly_target_test(prepared, spec)
    _atomic_private_json(report_path, report, pretty=True)
    report_path.chmod(0o600)
    return report
