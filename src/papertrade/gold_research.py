"""Research-only XAU/USD history and double-test workflow.

This module deliberately has no dependency on the operational instrument registry,
database, engine, or execution adapters.
"""
from __future__ import annotations

import hashlib
import json
import math
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from types import MappingProxyType
from typing import Any, Mapping

import httpx
import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression


SOURCE_ID = "algospecial_xauusd_m15_preview"
ALGOSPECIAL_OHLC_URL = "https://www.algospecial.com/api/ohlc.php"
EVIDENCE_WARNING = (
    "Historical research from an unidentified Exness-style MT5 feed; not OANDA, "
    "not a broker paper fill, and not evidence of future profitability."
)
GOLD_FEATURE_NAMES = (
    "return_1", "return_4", "return_16", "sma20_gap", "sma50_gap", "macd",
    "macd_signal", "rsi14", "atr", "atr_pct", "volatility", "momentum8",
    "volume_change", "volume_ratio", "price_range", "trend_strength", "regime",
)
GOLD_COST_POLICY = {
    "spread": "one full observed spread at entry and exit",
    "zero_spread_fallback": "development-only nonzero p99 (higher)",
    "slippage_bps_per_side": 2.0,
    "commission_bps_per_side": 1.0,
}
MINIMUM_CLOSED_TRADES = 200
GOLD_MODEL_PARAMETERS = {
    "n_estimators": 120,
    "num_leaves": 15,
    "max_depth": 5,
    "learning_rate": 0.04,
    "min_child_samples": 30,
    "reg_lambda": 2.0,
    "n_jobs": 1,
    "random_state": 42,
    "verbosity": -1,
    "deterministic": True,
    "force_col_wise": True,
}


@dataclass(frozen=True)
class GoldHistory:
    rows: tuple[Mapping[str, Any], ...]
    manifest: tuple[Mapping[str, Any], ...]

    def __post_init__(self):
        object.__setattr__(self, "rows", tuple(MappingProxyType(dict(row)) for row in self.rows))
        object.__setattr__(self, "manifest", tuple(MappingProxyType(dict(item)) for item in self.manifest))


@dataclass(frozen=True)
class PreparedGoldHistory:
    frame: pd.DataFrame
    manifest: tuple[Mapping[str, Any], ...]
    data_sha256: str
    source_id: str = SOURCE_ID


class AlgoSpecialGoldHistory:
    """Small-window client for the keyless AlgoSpecial preview endpoint."""

    def __init__(self, client: httpx.Client | None = None, sleeper=time.sleep):
        self._client = client or httpx.Client(timeout=30)
        self._sleeper = sleeper

    def fetch(self, start: date, end: date) -> GoldHistory:
        if end < start:
            raise ValueError("Gold history end date must not precede start date")
        rows: list[Mapping[str, Any]] = []
        manifest: list[Mapping[str, Any]] = []
        cursor = start
        while cursor <= end:
            chunk_end = min(cursor + timedelta(days=19), end)
            params = {"symbol": "XAUUSD", "tf": "M15", "from": cursor.isoformat(),
                      "to": chunk_end.isoformat(), "format": "json"}
            response = self._client.get(ALGOSPECIAL_OHLC_URL, params=params)
            if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", "60"))
                self._sleeper(retry_after)
                response = self._client.get(ALGOSPECIAL_OHLC_URL, params=params)
            response.raise_for_status()
            payload = response.json()
            chunk_rows = payload["data"]
            expected_metadata = {"symbol": "XAUUSD", "timeframe": "M15",
                                 "from": cursor.isoformat(), "to": chunk_end.isoformat()}
            if any(payload.get(key) != value for key, value in expected_metadata.items()) or (
                payload.get("rows") != len(chunk_rows)
            ):
                raise ValueError("AlgoSpecial response metadata does not match the request or returned rows")
            try:
                row_dates = [
                    datetime.strptime(row["Timestamp"], "%Y.%m.%d %H:%M:%S").date()
                    for row in chunk_rows
                ]
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError("AlgoSpecial response contains an invalid provider timestamp") from exc
            if any(stamp < cursor or stamp > chunk_end for stamp in row_dates):
                raise ValueError("AlgoSpecial response row lies outside its requested chunk")
            rows.extend(dict(row) for row in chunk_rows)
            manifest.append({
                "endpoint": ALGOSPECIAL_OHLC_URL,
                "request_start": cursor.isoformat(),
                "request_end": chunk_end.isoformat(),
                "symbol": "XAUUSD",
                "timeframe": "M15",
                "provider_clock": "broker server time; timezone unknown",
                "returned_rows": len(chunk_rows),
                "response_sha256": hashlib.sha256(_canonical_json(payload).encode()).hexdigest(),
            })
            cursor = chunk_end + timedelta(days=1)
        return GoldHistory(rows=tuple(rows), manifest=tuple(manifest))


def _canonical_json(value: Any) -> str:
    if isinstance(value, Mapping):
        value = {str(key): _json_value(item) for key, item in value.items()}
    else:
        value = _json_value(value)
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _json_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_value(item) for item in value]
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float):
        if math.isnan(value):
            return None
        if not math.isfinite(value):
            raise ValueError("Canonical evidence cannot contain an infinite number")
    return value


def _wilson_lower_bound(wins: int, count: int) -> float | None:
    if count == 0:
        return None
    z = 1.959963984540054
    observed = wins / count
    z_squared = z * z
    denominator = 1 + z_squared / count
    center = (observed + z_squared / (2 * count)) / denominator
    half_width = z * math.sqrt(
        observed * (1 - observed) / count + z_squared / (4 * count * count)
    ) / denominator
    return max(0.0, center - half_width)


def _bootstrap_lower_mean(values: list[float]) -> float | None:
    if len(values) < 5:
        return None
    observations = np.asarray(values, dtype=float)
    count = len(observations)
    block_length = max(2, int(math.sqrt(count)))
    generator = np.random.default_rng(42)
    sample_means = []
    for _ in range(1_000):
        blocks = []
        while sum(len(block) for block in blocks) < count:
            start = int(generator.integers(0, count))
            blocks.append(observations[(start + np.arange(block_length)) % count])
        sample_means.append(float(np.concatenate(blocks)[:count].mean()))
    return float(np.quantile(sample_means, 0.025))


def _summarize_replay(replay: Mapping[str, Any], minimum_trades: int) -> dict[str, Any]:
    net_pl = [float(trade["net_pl"]) for trade in replay["trades"]]
    count = len(net_pl)
    wins = sum(value > 0 for value in net_pl)
    win_rate = wins / count if count else None
    wilson = _wilson_lower_bound(wins, count)
    after_cost_net_pl = sum(net_pl)
    gross_profit = sum(value for value in net_pl if value > 0)
    gross_loss = -sum(value for value in net_pl if value < 0)
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else None
    profit_factor_gate = profit_factor > 1 if profit_factor is not None else gross_profit > 0
    equity = np.asarray(replay["equity"], dtype=float)
    if len(equity):
        peaks = np.maximum.accumulate(equity)
        drawdowns = np.divide(equity - peaks, peaks, out=np.zeros_like(equity), where=peaks != 0)
        max_drawdown = float(drawdowns.min())
        total_return = float(equity[-1] / equity[0] - 1) if equity[0] else 0.0
    else:
        max_drawdown = 0.0
        total_return = 0.0
    equity_returns = np.divide(
        np.diff(equity), equity[:-1], out=np.zeros(max(len(equity) - 1, 0)), where=equity[:-1] != 0
    )
    return_deviation = float(np.std(equity_returns, ddof=1)) if len(equity_returns) > 1 else 0.0
    sharpe = (
        math.sqrt(len(equity_returns)) * float(np.mean(equity_returns)) / return_deviation
        if return_deviation > 0 else None
    )
    bootstrap_lower = _bootstrap_lower_mean(net_pl)
    gates = {
        "point win rate above 50%": win_rate is not None and win_rate > 0.5,
        "Wilson 95% lower bound above 50%": wilson is not None and wilson > 0.5,
        "positive after-cost return": after_cost_net_pl > 0,
        "profit factor above one": profit_factor_gate,
        "provider-bar Sharpe above zero": sharpe is not None and sharpe > 0,
        "maximum drawdown no worse than -10%": max_drawdown >= -0.10,
        "positive bootstrap lower mean trade P/L": bootstrap_lower is not None and bootstrap_lower > 0,
        "outperform frozen rule": total_return > float(replay["rule_total_return"]),
        "outperform capped buy-and-hold": total_return > float(replay["buy_hold_total_return"]),
    }
    if count < minimum_trades:
        status = "inconclusive"
    else:
        status = "pass" if all(gates.values()) else "fail"
    return {
        "trade_count": count,
        "wins": wins,
        "win_rate": win_rate,
        "wilson_95_lower": wilson,
        "after_cost_net_pl": after_cost_net_pl,
        "total_return": total_return,
        "profit_factor": profit_factor,
        "profit_factor_gate": profit_factor_gate,
        "provider_bar_sharpe": sharpe,
        "max_drawdown": max_drawdown,
        "bootstrap_95_lower_mean_trade_pl": bootstrap_lower,
        "rule_total_return": float(replay["rule_total_return"]),
        "buy_hold_total_return": float(replay["buy_hold_total_return"]),
        "closed_trades": tuple(dict(trade) for trade in replay["trades"]),
        "trades_sha256": hashlib.sha256(_canonical_json(replay["trades"]).encode()).hexdigest(),
        "equity_curve": tuple(dict(point) for point in replay.get("equity_curve", ())),
        "equity_observations": len(equity),
        "equity_sha256": hashlib.sha256(_canonical_json(replay["equity"]).encode()).hexdigest(),
        "gates": gates,
        "status": status,
        "minimum_closed_trades": minimum_trades,
        "partition_sha256": replay["partition_sha256"],
    }


def gold_double_test_report(
    test_a: Mapping[str, Any],
    test_b: Mapping[str, Any],
    *,
    frozen: Mapping[str, Any],
) -> dict[str, Any]:
    """Build the deterministic, independent Test A/Test B evidence report."""
    a_summary = _summarize_replay(test_a, MINIMUM_CLOSED_TRADES)
    b_summary = _summarize_replay(test_b, MINIMUM_CLOSED_TRADES)
    statuses = (a_summary["status"], b_summary["status"])
    if "fail" in statuses:
        overall = "fail"
    elif "inconclusive" in statuses:
        overall = "inconclusive"
    else:
        overall = "pass"
    report = {
        "source_id": SOURCE_ID,
        "warning": EVIDENCE_WARNING,
        "frozen": dict(frozen),
        "test_a": a_summary,
        "test_b": b_summary,
        "overall_status": overall,
    }
    report["report_sha256"] = hashlib.sha256(_canonical_json(report).encode()).hexdigest()
    return report


def _price_only_features(segment: pd.DataFrame) -> pd.DataFrame:
    close = segment["close"].astype(float)
    returns = close.pct_change(fill_method=None)
    output = pd.DataFrame(index=segment.index)
    for bars in (1, 4, 16):
        output[f"return_{bars}"] = close.pct_change(bars, fill_method=None)
    output["sma20_gap"] = close / close.rolling(20).mean() - 1
    output["sma50_gap"] = close / close.rolling(50).mean() - 1
    ema12 = close.ewm(span=12, adjust=False, min_periods=12).mean()
    ema26 = close.ewm(span=26, adjust=False, min_periods=26).mean()
    output["macd"] = (ema12 - ema26) / close
    output["macd_signal"] = output["macd"].ewm(span=9, adjust=False, min_periods=9).mean()
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    rsi = 100 - 100 / (1 + gain / loss.replace(0, np.nan))
    rsi = rsi.mask((loss == 0) & (gain > 0), 100)
    output["rsi14"] = rsi.mask((loss == 0) & (gain == 0), 50)
    true_range = pd.concat([
        segment["high"] - segment["low"],
        (segment["high"] - close.shift()).abs(),
        (segment["low"] - close.shift()).abs(),
    ], axis=1).max(axis=1)
    output["atr"] = true_range.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    output["atr_pct"] = output["atr"] / close
    output["volatility"] = returns.rolling(20).std(ddof=1)
    output["momentum8"] = close.pct_change(8, fill_method=None)
    output["volume_change"] = (
        segment["volume"].pct_change(fill_method=None).replace([np.inf, -np.inf], np.nan).fillna(0)
    )
    mean_volume = segment["volume"].rolling(20).mean()
    output["volume_ratio"] = (segment["volume"] / mean_volume.replace(0, np.nan)).fillna(0)
    output["price_range"] = (segment["high"] - segment["low"]) / close
    output["trend_strength"] = (
        (close.rolling(20).mean() - close.rolling(50).mean()) / output["atr"].replace(0, np.nan)
    )
    output["regime"] = np.select([
        output["volatility"] > 0.015,
        output["trend_strength"] > 0.5,
        output["trend_strength"] < -0.5,
    ], [3, 1, 2], default=0)
    return output.replace([np.inf, -np.inf], np.nan).dropna()


def _gold_features(frame: pd.DataFrame) -> pd.DataFrame:
    pieces = [_price_only_features(segment) for _, segment in frame.groupby("segment", sort=False)]
    if not pieces:
        return pd.DataFrame(columns=GOLD_FEATURE_NAMES, index=frame.index[:0])
    return pd.concat(pieces).sort_index()[list(GOLD_FEATURE_NAMES)]


def _gold_labels(frame: pd.DataFrame) -> pd.DataFrame:
    exit_time = pd.Series(frame.index, index=frame.index).shift(-5)
    same_segment = frame["segment"].eq(frame["segment"].shift(-5))
    consecutive = exit_time.sub(frame.index.to_series()).eq(pd.to_timedelta(75, unit="min"))
    gross = (frame["open"].shift(-5) / frame["open"].shift(-1) - 1).where(
        same_segment & consecutive
    )
    labels = pd.DataFrame({"gross_return": gross}).dropna()
    labels["label"] = (labels["gross_return"] > 0).astype(int)
    return labels


def _frame_sha256(frame: pd.DataFrame) -> str:
    records = frame.reset_index().copy()
    if "provider_time" in records:
        records["provider_time"] = records["provider_time"].dt.strftime("%Y-%m-%dT%H:%M:%S")
    return hashlib.sha256(_canonical_json(records.to_dict("records")).encode()).hexdigest()


def _prepared_data_sha256(frame: pd.DataFrame, manifest: tuple[Mapping[str, Any], ...]) -> str:
    canonical_rows = frame.reset_index().assign(
        provider_time=lambda value: value.provider_time.dt.strftime("%Y-%m-%dT%H:%M:%S")
    ).to_dict("records")
    return hashlib.sha256(_canonical_json({
        "source_id": SOURCE_ID,
        "manifest": manifest,
        "rows": canonical_rows,
    }).encode()).hexdigest()


def _logit(probability: np.ndarray) -> np.ndarray:
    clipped = np.clip(probability, 1e-7, 1 - 1e-7)
    return np.log(clipped / (1 - clipped))


def _fit_gold_model(train: pd.DataFrame, calibration: pd.DataFrame):
    if train["label"].nunique() < 2 or calibration["label"].nunique() < 2:
        raise ValueError("Gold training and calibration partitions each require both label classes")
    model = lgb.LGBMClassifier(**GOLD_MODEL_PARAMETERS)
    model.fit(train[list(GOLD_FEATURE_NAMES)], train["label"])
    calibration_logits = _logit(
        model.predict_proba(calibration[list(GOLD_FEATURE_NAMES)])[:, 1]
    ).reshape(-1, 1)
    calibrator = LogisticRegression(C=1e6, random_state=42, max_iter=1000)
    calibrator.fit(calibration_logits, calibration["label"])
    calibration_parameters = {
        "method": "sigmoid",
        "coefficient": float(calibrator.coef_[0, 0]),
        "intercept": float(calibrator.intercept_[0]),
    }
    return model, calibration_parameters


def _gold_probabilities(model, calibration: Mapping[str, float], features: pd.DataFrame) -> pd.Series:
    raw = model.predict_proba(features[list(GOLD_FEATURE_NAMES)])[:, 1]
    z = np.clip(
        _logit(raw) * calibration["coefficient"] + calibration["intercept"], -40, 40
    )
    return pd.Series(1 / (1 + np.exp(-z)), index=features.index)


def _spread_or_fallback(value: Any, fallback: float) -> float:
    spread = float(value) if value is not None and pd.notna(value) else 0.0
    return spread if spread > 0 else fallback


def _gold_replay(
    frame: pd.DataFrame,
    signals: pd.Series,
    partition: pd.DataFrame,
    spread_fallback: float,
) -> dict[str, Any]:
    position_for_time = {provider_time: position for position, provider_time in enumerate(frame.index)}
    start, end = partition.index[0], partition.index[-1]
    trades: list[dict[str, Any]] = []
    last_exit_position = -1
    for provider_time, selected in signals.items():
        if not bool(selected):
            continue
        signal_position = position_for_time[provider_time]
        if signal_position < last_exit_position or signal_position + 5 >= len(frame):
            continue
        entry_position, exit_position = signal_position + 1, signal_position + 5
        entry_time, exit_time = frame.index[entry_position], frame.index[exit_position]
        if entry_time < start or exit_time > end:
            continue
        if frame["segment"].iloc[signal_position] != frame["segment"].iloc[exit_position]:
            continue
        if exit_time - provider_time != pd.to_timedelta(75, unit="min"):
            continue
        entry_open = float(frame["open"].iloc[entry_position])
        exit_open = float(frame["open"].iloc[exit_position])
        entry_spread = _spread_or_fallback(frame["spread_usd"].iloc[entry_position], spread_fallback)
        exit_spread = _spread_or_fallback(frame["spread_usd"].iloc[exit_position], spread_fallback)
        slippage = GOLD_COST_POLICY["slippage_bps_per_side"] / 10_000
        commission = GOLD_COST_POLICY["commission_bps_per_side"] / 10_000
        entry_fill = entry_open + entry_spread + entry_open * slippage
        exit_fill = exit_open - exit_spread - exit_open * slippage
        commission_usd = entry_fill * commission + exit_fill * commission
        net_pl = exit_fill - entry_fill - commission_usd
        trades.append({
            "signal_provider_time": provider_time.isoformat(),
            "entry_provider_time": entry_time.isoformat(),
            "exit_provider_time": exit_time.isoformat(),
            "entry_open": entry_open,
            "exit_open": exit_open,
            "entry_fill": entry_fill,
            "exit_fill": exit_fill,
            "entry_spread_usd": entry_spread,
            "exit_spread_usd": exit_spread,
            "commission_usd": commission_usd,
            "entry_commission_usd": entry_fill * commission,
            "net_pl": net_pl,
        })
        last_exit_position = exit_position
    partition_frame = frame.loc[start:end]
    entries = {pd.Timestamp(trade["entry_provider_time"]): trade for trade in trades}
    exits = {pd.Timestamp(trade["exit_provider_time"]): trade for trade in trades}
    active_trade = None
    realized_pl = 0.0
    equity_curve = []
    for provider_time, row in partition_frame.iterrows():
        if provider_time in exits:
            realized_pl += exits[provider_time]["net_pl"]
            active_trade = None
        if provider_time in entries:
            active_trade = entries[provider_time]
        unrealized_pl = 0.0
        if active_trade is not None:
            mark = float(row["close"])
            liquidation = mark - _spread_or_fallback(row["spread_usd"], spread_fallback) - mark * slippage
            unrealized_pl = (
                liquidation - active_trade["entry_fill"] - active_trade["entry_commission_usd"]
                - liquidation * commission
            )
        equity_curve.append({"provider_time": provider_time.isoformat(),
                             "equity": 10_000.0 + realized_pl + unrealized_pl})
    equity = tuple(point["equity"] for point in equity_curve)
    return {
        "trades": tuple(trades),
        "equity": equity,
        "equity_curve": tuple(equity_curve),
        "rule_total_return": 0.0,
        "buy_hold_total_return": 0.0,
        "partition_sha256": _frame_sha256(partition_frame),
    }


def _gold_buy_hold_return(
    frame: pd.DataFrame,
    partition: pd.DataFrame,
    spread_fallback: float,
) -> float:
    total_net_pl = 0.0
    interval = frame.loc[partition.index[0]:partition.index[-1]]
    slippage = GOLD_COST_POLICY["slippage_bps_per_side"] / 10_000
    commission = GOLD_COST_POLICY["commission_bps_per_side"] / 10_000
    for _, segment in interval.groupby("segment", sort=False):
        if len(segment) < 2:
            continue
        entry_row, exit_row = segment.iloc[1], segment.iloc[-1]
        entry_open, exit_open = float(entry_row["open"]), float(exit_row["open"])
        entry_fill = entry_open + _spread_or_fallback(entry_row["spread_usd"], spread_fallback) + entry_open * slippage
        exit_fill = exit_open - _spread_or_fallback(exit_row["spread_usd"], spread_fallback) - exit_open * slippage
        total_net_pl += exit_fill - entry_fill - (entry_fill + exit_fill) * commission
    return total_net_pl / 10_000


def _with_gold_benchmarks(
    replay: dict[str, Any],
    frame: pd.DataFrame,
    features: pd.DataFrame,
    partition: pd.DataFrame,
    spread_fallback: float,
) -> dict[str, Any]:
    partition_features = features.loc[partition.index]
    rule_signals = (
        partition_features["sma20_gap"].gt(0)
        & partition_features["return_4"].gt(0)
        & partition_features["regime"].eq(1)
        & partition_features["rsi14"].lt(80)
    )
    rule = _gold_replay(frame, rule_signals, partition, spread_fallback)
    replay["rule_total_return"] = sum(trade["net_pl"] for trade in rule["trades"]) / 10_000
    replay["buy_hold_total_return"] = _gold_buy_hold_return(frame, partition, spread_fallback)
    return replay


def _partition_description(partition: pd.DataFrame) -> dict[str, Any]:
    return {
        "rows": len(partition),
        "start_provider_time": partition.index[0].isoformat(),
        "end_provider_time": partition.index[-1].isoformat(),
        "sha256": _frame_sha256(partition),
    }


def run_gold_double_test(prepared: PreparedGoldHistory) -> dict[str, Any]:
    """Fit once on development data, then evaluate locked Test A and Test B."""
    frame = prepared.frame
    if _prepared_data_sha256(frame, prepared.manifest) != prepared.data_sha256:
        raise ValueError("Prepared gold history changed after preparation")
    features = _gold_features(frame)
    labels = _gold_labels(frame)
    joined = features.join(labels, how="inner").dropna()
    if len(joined) < 600:
        raise ValueError("Gold double test requires at least 600 usable labeled M15 bars")
    count = len(joined)
    a, b, c, d = int(count * 0.50), int(count * 0.65), int(count * 0.80), int(count * 0.90)
    gap = 5
    train = joined.iloc[:a - gap]
    calibration = joined.iloc[a:b - gap]
    validation = joined.iloc[b:c - gap]
    test_a = joined.iloc[c:d - gap]
    test_b = joined.iloc[d:]
    partitions = {
        "train": train,
        "calibration": calibration,
        "threshold_validation": validation,
        "test_a": test_a,
        "test_b": test_b,
    }
    if any(partition.empty for partition in partitions.values()):
        raise ValueError("Gold double-test partitions must all be non-empty")
    model, calibration_parameters = _fit_gold_model(train, calibration)
    probabilities = _gold_probabilities(model, calibration_parameters, joined)
    development_end = validation.index[-1]
    nonzero_development_spreads = frame.loc[:development_end, "spread_usd"]
    nonzero_development_spreads = nonzero_development_spreads[
        nonzero_development_spreads.gt(0) & np.isfinite(nonzero_development_spreads)
    ]
    if nonzero_development_spreads.empty:
        raise ValueError("Development data requires a nonzero spread for the frozen fallback")
    spread_fallback = float(np.quantile(nonzero_development_spreads, 0.99, method="higher"))
    threshold_grid = (0.55, 0.60, 0.65, 0.70, 0.75)
    threshold = threshold_grid[0]
    best_score = -float("inf")
    for candidate in threshold_grid:
        trial = _gold_replay(
            frame,
            probabilities.loc[validation.index].ge(candidate),
            validation,
            spread_fallback,
        )
        score = sum(trade["net_pl"] for trade in trial["trades"])
        if score > best_score:
            best_score, threshold = score, candidate
    train_and_calibration = pd.concat([train, calibration])
    model_material = {
        "booster": model.booster_.model_to_string(),
        "calibration": calibration_parameters,
        "feature_names": GOLD_FEATURE_NAMES,
        "parameters": GOLD_MODEL_PARAMETERS,
        "fit_data_sha256": _frame_sha256(train_and_calibration),
    }
    model_sha256 = hashlib.sha256(_canonical_json(model_material).encode()).hexdigest()
    development_sha256 = _frame_sha256(pd.concat([train, calibration, validation]))
    cost_policy_sha256 = hashlib.sha256(_canonical_json(GOLD_COST_POLICY).encode()).hexdigest()
    threshold_material = {
        "model_sha256": model_sha256,
        "threshold": threshold,
        "grid": threshold_grid,
        "selection": "highest validation after-cost P/L; lowest threshold wins ties",
        "cost_policy_sha256": cost_policy_sha256,
        "development_sha256": development_sha256,
    }
    threshold_sha256 = hashlib.sha256(_canonical_json(threshold_material).encode()).hexdigest()
    frozen = {
        "model": "LightGBM LGBMClassifier with sigmoid calibration",
        "model_parameters": dict(GOLD_MODEL_PARAMETERS),
        "calibration": calibration_parameters,
        "model_sha256": model_sha256,
        "development_sha256": development_sha256,
        "threshold_sha256": threshold_sha256,
        "threshold": threshold,
        "threshold_grid": threshold_grid,
        "threshold_selection": threshold_material["selection"],
        "cost_policy_sha256": cost_policy_sha256,
        "development_spread_p99_usd": spread_fallback,
        "purge_bars": gap,
        "horizon_bars": 4,
    }
    replay_a = _with_gold_benchmarks(
        _gold_replay(frame, probabilities.loc[test_a.index].ge(threshold), test_a, spread_fallback),
        frame, features, test_a, spread_fallback,
    )
    replay_b = _with_gold_benchmarks(
        _gold_replay(frame, probabilities.loc[test_b.index].ge(threshold), test_b, spread_fallback),
        frame, features, test_b, spread_fallback,
    )
    report = gold_double_test_report(replay_a, replay_b, frozen=frozen)
    report.pop("report_sha256")
    report.update({
        "data_sha256": prepared.data_sha256,
        "manifest": tuple(dict(item) for item in prepared.manifest),
        "provider_time": "broker server time; timezone unknown",
        "feature_names": list(GOLD_FEATURE_NAMES),
        "cost_policy": dict(GOLD_COST_POLICY),
        "benchmarks": {
            "rule": "positive four-bar momentum above SMA20 in uptrend with RSI below 80; identical costs",
            "capped_buy_hold": "one ounce per contiguous segment; identical costs; no gap financing",
        },
        "partitions": {name: _partition_description(value) for name, value in partitions.items()},
    })
    report["report_sha256"] = hashlib.sha256(_canonical_json(report).encode()).hexdigest()
    return report


def prepare_gold_history(history: GoldHistory) -> PreparedGoldHistory:
    """Parse source rows without assigning a timezone to the provider's clock."""
    frame = pd.DataFrame(history.rows).rename(columns={
        "Open": "open",
        "High": "high",
        "Low": "low",
        "Close": "close",
        "TickVolume": "volume",
        "Spread": "spread_points",
    })
    provider_time = pd.to_datetime(frame.pop("Timestamp"), format="%Y.%m.%d %H:%M:%S", errors="raise")
    frame.index = pd.DatetimeIndex(provider_time, name="provider_time")
    if frame.empty:
        raise ValueError("Gold history contains no rows")
    if not frame.index.is_unique or not frame.index.is_monotonic_increasing:
        raise ValueError("Provider times must be unique and strictly increasing")
    price_columns = ["open", "high", "low", "close"]
    frame[price_columns] = frame[price_columns].astype(float)
    prices = frame[price_columns].to_numpy()
    if not np.isfinite(prices).all() or (prices <= 0).any():
        raise ValueError("Gold history requires finite positive prices")
    invalid_ohlc = (
        frame["high"].lt(frame[price_columns].max(axis=1))
        | frame["low"].gt(frame[price_columns].min(axis=1))
    )
    if invalid_ohlc.any():
        raise ValueError("Gold history violates OHLC invariants")
    frame["volume"] = pd.to_numeric(frame["volume"], errors="raise")
    if not np.isfinite(frame["volume"]).all() or frame["volume"].lt(0).any():
        raise ValueError("Gold history requires finite nonnegative tick volume")
    frame["spread_points"] = pd.to_numeric(frame["spread_points"], errors="raise")
    observed_spread = frame["spread_points"].dropna()
    if not np.isfinite(observed_spread).all() or observed_spread.lt(0).any():
        raise ValueError("Gold history requires finite nonnegative spread points when observed")
    frame["spread_usd"] = frame["spread_points"].astype(float) * 0.001
    gaps = frame.index.to_series().diff().ne(pd.to_timedelta(15, unit="min"))
    gaps.iloc[0] = False
    frame["segment"] = gaps.cumsum().astype(int).to_numpy()
    digest = _prepared_data_sha256(frame, history.manifest)
    return PreparedGoldHistory(frame=frame.copy(deep=True), manifest=history.manifest, data_sha256=digest)
