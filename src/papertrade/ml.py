"""LightGBM research pipeline with chronological calibration and explicit candidate promotion.

Artifacts use native LightGBM text and JSON; inference never unpickles executable Python.
One-hour labels begin at the NEXT bar's opening price, after the decision is observable.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import tempfile
from dataclasses import asdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
import sklearn
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score
from sklearn.model_selection import TimeSeriesSplit

from papertrade.backtest import performance_metrics, run_backtest
from papertrade.config import Settings
from papertrade.data import validate_candles
from papertrade.domain import INSTRUMENTS, Instrument, utcnow
from papertrade.features import FEATURE_VERSION, build_features, feature_regime


class ModelError(RuntimeError):
    pass


@dataclass(frozen=True)
class Prediction:
    probability: float
    expected_return: float
    regime: str
    model_version: str
    atr: float
    volatility: float
    threshold: float


def make_labels(candles: pd.DataFrame, horizon: int = 4) -> pd.DataFrame:
    if horizon < 1:
        raise ValueError("Positive label horizon required")
    gross = candles.open.shift(-(horizon + 1)) / candles.open.shift(-1) - 1
    # Do not label positions that would span missing candles or a closed market.
    future_index = pd.Series(candles.index, index=candles.index).shift(-(horizon + 1))
    consecutive = future_index - candles.index.to_series() == pd.Timedelta(minutes=15 * (horizon + 1))
    gross = gross.where(consecutive).dropna()
    return pd.DataFrame({"gross_return": gross, "label": (gross > 0).astype(int)})


def _logit(probability):
    clipped = np.clip(probability, 1e-7, 1 - 1e-7)
    return np.log(clipped / (1 - clipped))


def _calibrated(raw, calibration):
    z = np.clip(_logit(raw) * calibration["coefficient"] + calibration["intercept"], -40, 40)
    return 1 / (1 + np.exp(-z))


def _fit(x, y, calibration_x, calibration_y, params):
    if y.nunique() < 2 or calibration_y.nunique() < 2:
        raise ModelError("Training and calibration each require both label classes")
    model = lgb.LGBMClassifier(**params)
    model.fit(x, y)
    logits = _logit(model.predict_proba(calibration_x)[:, 1]).reshape(-1, 1)
    calibrator = LogisticRegression(C=1e6, random_state=42, max_iter=1000)
    calibrator.fit(logits, calibration_y)
    return model, {"method": "sigmoid", "coefficient": float(calibrator.coef_[0, 0]),
                   "intercept": float(calibrator.intercept_[0])}


def _expected(probabilities, positive_mean, negative_mean):
    return probabilities * positive_mean + (1 - probabilities) * negative_mean


def _buy_hold(candles, instrument, start, end, capital):
    frame = candles.loc[start:end]
    # At start close a decision can be made, so buy at the second row open.
    if len(frame) < 2:
        raise ModelError("Insufficient benchmark period")
    spread = instrument.max_spread_bps / 2
    impact = (spread / 2 + instrument.slippage_bps) / 10000
    fees = instrument.fee_bps / 10000
    entry = float(frame.open.iloc[1]) * (1 + impact)
    qty = math.floor(capital * instrument.max_exposure / entry / instrument.qty_step) * instrument.qty_step
    if qty < instrument.min_qty:
        qty = 0
    entry_fee = qty * entry * fees
    cash = capital - qty * entry - entry_fee
    equity = cash + qty * frame.close
    equity.iloc[0] = capital
    exit_price = float(frame.close.iloc[-1]) * (1 - impact)
    exit_fee = qty * exit_price * fees
    equity.iloc[-1] = cash + qty * exit_price - exit_fee
    net = qty * (exit_price - entry) - entry_fee - exit_fee
    trades = [{"net_pl": net}] if qty > 0 else []
    return {"metrics": performance_metrics(equity, trades), "capital_allocation": instrument.max_exposure,
            "description": "single long holding; identical maximum instrument capital allocation; estimated costs"}


def _evaluation(candles, instrument, probs, expected, threshold, start, end, settings):
    report = run_backtest(candles, probs, instrument, threshold=threshold, expected_returns=expected,
                          start=start, end=end, min_edge_bps=settings.min_net_edge_bps,
                          risk_per_trade=settings.risk_per_trade, daily_loss_limit=settings.daily_loss_limit,
                          max_drawdown=settings.max_drawdown, initial_cash=settings.capital, settings=settings)
    features = build_features(candles)
    rule = pd.Series(np.where((features.sma20_gap > 0) & (features.return_4 > 0) &
                              (features.regime == 1) & (features.rsi14 < 80), .99, .01), index=features.index)
    baseline = run_backtest(candles, rule, instrument, threshold=.6, start=start, end=end,
                            expected_returns=features.return_4, initial_cash=settings.capital, settings=settings,
                            risk_per_trade=settings.risk_per_trade, daily_loss_limit=settings.daily_loss_limit,
                            max_drawdown=settings.max_drawdown)
    return report, {"rule": {"metrics": baseline["metrics"], "description": "positive 4-bar momentum above SMA20 in uptrend; RSI<80"},
                    "buy_hold": _buy_hold(candles, instrument, start, end, settings.capital)}


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _write_json(path, value):
    path = Path(path)
    temp = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    temp.write_text(json.dumps(value, indent=2, allow_nan=False, sort_keys=True))
    os.replace(temp, path)


def _model_dir(symbol, settings):
    if symbol not in INSTRUMENTS:
        raise ModelError("Unsupported model symbol")
    return Path(settings.models_dir) / symbol.replace("/", "_")


def validation_policy(instrument: Instrument, settings: Settings) -> dict:
    """Pin candidate validation to the same costs, limits and decision implementation.

    An operator must retrain after changing execution mode, risk configuration, or
    trading-policy source. Credentials, paths and dashboard settings are excluded.
    """
    keys = ("execution", "capital", "risk_per_trade", "daily_loss_limit", "max_drawdown", "max_positions",
            "max_total_exposure", "max_instrument_exposure", "max_correlated_exposure",
            "max_data_age_seconds", "max_quote_age_seconds", "min_probability", "min_net_edge_bps",
            "min_validation_trades", "allow_unhosted_protection")
    source = Path(__file__).parent
    policy = {"version": "long_only_horizon4_v2", "instrument": asdict(instrument),
              "settings": {key: getattr(settings, key) for key in keys},
              "source_sha256": {name: _sha(source / name) for name in
                                 ("decisions.py", "risk.py", "features.py", "backtest.py", "ml.py", "calendars.py", "data.py")}}
    policy["sha256"] = hashlib.sha256(json.dumps(policy, sort_keys=True, allow_nan=False).encode()).hexdigest()
    return policy


def train_model(candles: pd.DataFrame, instrument: Instrument, settings: Settings,
                 now: datetime | None = None, params: dict | None = None) -> dict:
    now = now or utcnow()
    policy = validation_policy(instrument, settings)
    candles = validate_candles(candles, now, instrument.market)
    features = build_features(candles)
    labels = make_labels(candles)
    joined = features.join(labels, how="inner").dropna()
    if len(joined) < 600:
        raise ModelError("At least 600 usable labeled candles are required; collect more history")
    names = list(features.columns)
    x = joined[names]
    n = len(joined)
    gap = 5  # Four-bar holding horizon plus next-bar entry.
    a, b, c = int(n * .50), int(n * .65), int(n * .80)
    train, calibration, validation, test = (joined.iloc[:a-gap], joined.iloc[a:b-gap],
                                           joined.iloc[b:c-gap], joined.iloc[c:])
    hyperparameters = {"n_estimators": 120, "num_leaves": 15, "max_depth": 5, "learning_rate": .04,
                       "min_child_samples": 30, "reg_lambda": 2., "n_jobs": 1, "random_state": 42,
                       "verbosity": -1, "deterministic": True, "force_col_wise": True}
    if params:
        allowed = {"n_estimators", "num_leaves", "max_depth", "learning_rate", "min_child_samples", "reg_lambda"}
        if not set(params) <= allowed:
            raise ModelError("Only documented model hyperparameters may be overridden")
        hyperparameters.update(params)
    data_digest = hashlib.sha256(pd.util.hash_pandas_object(candles, index=True).to_numpy().tobytes()).hexdigest()
    content_digest = hashlib.sha256((data_digest + json.dumps(hyperparameters, sort_keys=True) + policy["sha256"]).encode()).hexdigest()[:12]
    version = candles.index[-1].strftime("%Y%m%dT%H%M%S") + "-" + content_digest
    final_folder = _model_dir(instrument.symbol, settings) / version
    if final_folder.exists():
        # Repeating the identical training request cannot overwrite or refresh an artifact.
        return _load(instrument.symbol, settings, version)[2]
    model, calibration_params = _fit(train[names], train.label, calibration[names], calibration.label, hyperparameters)
    positive_mean = float(train.loc[train.label == 1, "gross_return"].mean())
    negative_mean = float(train.loc[train.label == 0, "gross_return"].mean())
    raw = model.predict_proba(x)[:, 1]
    probabilities = pd.Series(_calibrated(raw, calibration_params), index=x.index)
    expected = _expected(probabilities, positive_mean, negative_mean)
    # Tune a small, declared threshold grid using VALIDATION only, then freeze it.
    selected_threshold = max(settings.min_probability, .60)
    best_score = -float("inf")
    for threshold in (.55, .60, .65, .70, .75):
        if threshold < settings.min_probability:
            continue
        trial = run_backtest(candles, probabilities, instrument, threshold=threshold, expected_returns=expected,
                              start=validation.index[0], end=validation.index[-1], min_edge_bps=settings.min_net_edge_bps,
                              risk_per_trade=settings.risk_per_trade, daily_loss_limit=settings.daily_loss_limit,
                              max_drawdown=settings.max_drawdown, initial_cash=settings.capital, settings=settings)
        score = trial["metrics"]["total_return"] if trial["metrics"]["trade_count"] >= settings.min_validation_trades else -float("inf")
        if score > best_score:
            best_score, selected_threshold = score, threshold
    validation_report, validation_benchmarks = _evaluation(candles, instrument, probabilities, expected, selected_threshold,
                                                            validation.index[0], validation.index[-1], settings)
    report, benchmarks = _evaluation(candles, instrument, probabilities, expected, selected_threshold,
                                     test.index[0], test.index[-1], settings)
    # Expanding chronological walk-forward fits, all confined to the pre-test development period.
    walk_forward = []
    development = joined.iloc[:c-gap]
    for fold, (fit_index, evaluation_index) in enumerate(TimeSeriesSplit(n_splits=3, gap=gap).split(development)):
        fit_data, evaluation = development.iloc[fit_index], development.iloc[evaluation_index]
        cut = int(len(fit_data) * .75)
        subtrain, subcal = fit_data.iloc[:cut-gap], fit_data.iloc[cut:]
        try:
            fold_model, fold_cal = _fit(subtrain[names], subtrain.label, subcal[names], subcal.label, hyperparameters)
            fold_prob = pd.Series(_calibrated(fold_model.predict_proba(evaluation[names])[:, 1], fold_cal), index=evaluation.index)
            win = float(subtrain.loc[subtrain.label == 1, "gross_return"].mean())
            loss = float(subtrain.loc[subtrain.label == 0, "gross_return"].mean())
            # The final threshold was tuned later than these historical folds. Use
            # the predeclared configuration here, never a future-selected value.
            fold_report = run_backtest(candles, fold_prob, instrument, threshold=settings.min_probability,
                                       expected_returns=_expected(fold_prob, win, loss),
                                       start=evaluation.index[0], end=evaluation.index[-1],
                                       min_edge_bps=settings.min_net_edge_bps, initial_cash=settings.capital, settings=settings)
            walk_forward.append({"fold": fold + 1, "train_end": subtrain.index[-1].isoformat(),
                                 "calibration_end": subcal.index[-1].isoformat(),
                                 "test_start": evaluation.index[0].isoformat(), "test_end": evaluation.index[-1].isoformat(),
                                 "threshold": settings.min_probability,
                                 "metrics": fold_report["metrics"]})
        except ModelError as exc:
            walk_forward.append({"fold": fold + 1, "error": str(exc), "metrics": {"total_return": 0, "trade_count": 0}})
    test_probability = probabilities.loc[test.index]
    brier = float(brier_score_loss(test.label, test_probability))
    null_brier = float(brier_score_loss(test.label, np.full(len(test), float(train.label.mean()))))
    profits = np.array([trade["net_pl"] for trade in report["trades"]])
    lower_pl = None
    if len(profits) >= 5:
        generator = np.random.default_rng(42)
        samples = generator.choice(profits, size=(1000, len(profits)), replace=True).mean(axis=1)
        lower_pl = float(np.quantile(samples, .025))
    failures = []
    metrics = report["metrics"]
    checks = {
        "minimum out-of-sample trade count": metrics["trade_count"] >= settings.min_validation_trades,
        "minimum validation trade count": validation_report["metrics"]["trade_count"] >= settings.min_validation_trades,
        "positive validation net return": validation_report["metrics"]["total_return"] > 0,
        "positive out-of-sample net return": metrics["total_return"] > 0,
        "outperform rule baseline": metrics["total_return"] > benchmarks["rule"]["metrics"]["total_return"],
        "outperform capped buy-and-hold": metrics["total_return"] > benchmarks["buy_hold"]["metrics"]["total_return"],
        "maximum drawdown": metrics["max_drawdown"] >= -settings.max_drawdown,
        "positive risk-adjusted return": metrics["sharpe"] > 0,
        "calibration better than class prior": brier <= null_brier,
        "positive bootstrap lower mean P/L": lower_pl is not None and lower_pl > 0,
        "majority profitable walk-forward folds": sum(f["metrics"]["total_return"] > 0 for f in walk_forward) >= 2,
    }
    failures = [name for name, passed in checks.items() if not passed]
    if validation_policy(instrument, settings)["sha256"] != policy["sha256"]:
        raise ModelError("Trading policy changed during training; retry against stable configuration")
    directory = _model_dir(instrument.symbol, settings)
    directory.mkdir(parents=True, exist_ok=True)
    folder = Path(tempfile.mkdtemp(prefix=f".{version}.", dir=directory))
    booster_path, calibration_path = folder / "booster.txt", folder / "calibration.json"
    model.booster_.save_model(str(booster_path))
    _write_json(calibration_path, calibration_params)
    metadata = {
        "symbol": instrument.symbol, "market": instrument.market, "version": version, "algorithm": "LightGBM",
        "trained_at": now.astimezone(timezone.utc).isoformat(), "data_sha256": data_digest,
        "data_start": candles.index[0].isoformat(), "data_end": candles.index[-1].isoformat(),
        "feature_version": FEATURE_VERSION, "feature_names": names, "horizon": 4,
        "validation_policy": policy,
        "params": hyperparameters, "threshold": selected_threshold, "positive_mean": positive_mean,
        "negative_mean": negative_mean, "accepted": not failures, "validation_failures": failures,
        "criteria": checks, "bootstrap_mean_pl_lower_95": lower_pl,
        "split": {"train_end": train.index[-1].isoformat(), "calibration_start": calibration.index[0].isoformat(),
                  "calibration_end": calibration.index[-1].isoformat(), "validation_start": validation.index[0].isoformat(),
                  "validation_end": validation.index[-1].isoformat(), "test_start": test.index[0].isoformat(), "test_end": test.index[-1].isoformat(),
                  "purge_bars": gap},
        "classification": {"brier": brier, "class_prior_brier": null_brier,
                           "log_loss": float(log_loss(test.label, test_probability, labels=[0, 1])),
                           "roc_auc": float(roc_auc_score(test.label, test_probability)) if test.label.nunique() > 1 else None},
        "validation": validation_report["metrics"], "validation_benchmarks": validation_benchmarks,
        "test": metrics, "benchmarks": benchmarks, "walk_forward": walk_forward,
        "libraries": {"lightgbm": lgb.__version__, "scikit_learn": sklearn.__version__, "pandas": pd.__version__},
        "hashes": {"booster.txt": _sha(booster_path), "calibration.json": _sha(calibration_path)},
        "limitations": ["Free historical bars do not provide observed spreads; fees, spread and slippage are assumptions",
                        "OHLC stop-first path approximation; no order-book queue simulation",
                        "Fixed present-day six-instrument universe, no delisted assets; no generalization beyond this universe",
                        "Bootstrap is an approximate diagnostic and does not establish future profitability"],
    }
    _write_json(folder / "metadata.json", metadata)
    _write_json(folder / "test_backtest.json", report)
    try:
        os.rename(folder, final_folder)
    except OSError:
        shutil.rmtree(folder)
        if final_folder.is_dir():
            return _load(instrument.symbol, settings, version)[2]
        raise ModelError("Unable to commit immutable model candidate") from None
    return metadata


def _load(symbol, settings, version=None, active_required=False):
    directory = _model_dir(symbol, settings)
    try:
        pointer = None
        if version is None:
            pointer = json.loads((directory / "active.json").read_text())
            version = pointer["version"]
        if not isinstance(version, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", version):
            raise ModelError("Invalid model version")
        folder = directory / version
        metadata = json.loads((folder / "metadata.json").read_text())
        if metadata["symbol"] != symbol or metadata["version"] != version or metadata["feature_version"] != FEATURE_VERSION:
            raise ModelError("Model metadata is incompatible")
        if metadata["validation_policy"]["sha256"] != validation_policy(INSTRUMENTS[symbol], settings)["sha256"]:
            raise ModelError("Trading validation policy changed; retraining required")
        if pointer is not None and pointer["metadata_sha256"] != _sha(folder / "metadata.json"):
            raise ModelError("Active model metadata integrity failure")
        for name in ("booster.txt", "calibration.json"):
            if _sha(folder / name) != metadata["hashes"][name]:
                raise ModelError("Model artifact integrity failure")
        if active_required and (not metadata["accepted"] or not all(metadata["criteria"].values())):
            raise ModelError("Model has not passed validation")
        booster = lgb.Booster(model_file=str(folder / "booster.txt"))
        calibration = json.loads((folder / "calibration.json").read_text())
        if booster.feature_name() != metadata["feature_names"]:
            raise ModelError("Model feature names differ from metadata")
        return booster, calibration, metadata
    except (FileNotFoundError, KeyError, ValueError, TypeError, lgb.basic.LightGBMError) as exc:
        raise ModelError("Missing or invalid active model/artifact") from exc


def promote_model(symbol: str, version: str, settings: Settings) -> dict:
    _, _, metadata = _load(symbol, settings, version, active_required=True)
    age = utcnow() - datetime.fromisoformat(metadata["trained_at"])
    if age.total_seconds() < -60 or age.days > settings.model_max_age_days:
        raise ModelError("Candidate is outdated or has a future timestamp")
    directory = _model_dir(symbol, settings)
    _write_json(directory / "active.json", {"version": version, "metadata_sha256": _sha(directory / version / "metadata.json")})
    return metadata


def predict(candles: pd.DataFrame, instrument: Instrument, settings: Settings,
             now: datetime | None = None) -> Prediction:
    now = now or utcnow()
    booster, calibration, metadata = _load(instrument.symbol, settings, active_required=True)
    if metadata["validation_policy"]["sha256"] != validation_policy(instrument, settings)["sha256"]:
        raise ModelError("Instrument validation policy changed; retraining required")
    age = now - datetime.fromisoformat(metadata["trained_at"])
    data_age = now - datetime.fromisoformat(metadata["data_end"])
    if age.total_seconds() < -60 or age.days > settings.model_max_age_days or data_age.days > settings.model_max_age_days:
        raise ModelError("Active model is outdated")
    candles = validate_candles(candles, now, instrument.market, require_fresh=True,
                              max_age_seconds=settings.max_data_age_seconds)
    features = build_features(candles)
    if features.empty or features.index[-1] != candles.index[-1] or list(features.columns) != metadata["feature_names"]:
        raise ModelError("Insufficient or incompatible inference features")
    probability = float(_calibrated(booster.predict(features.iloc[-1:]), calibration)[0])
    expected = float(_expected(probability, metadata["positive_mean"], metadata["negative_mean"]))
    if not np.isfinite([probability, expected]).all() or not 0 <= probability <= 1:
        raise ModelError("Invalid model output")
    row = features.iloc[-1]
    return Prediction(probability, expected, feature_regime(row), metadata["version"],
                      float(row.atr), float(row.volatility), float(metadata["threshold"]))


def backtest_saved_model(candles: pd.DataFrame, instrument: Instrument, settings: Settings,
                          version: str | None = None) -> dict:
    booster, calibration, metadata = _load(instrument.symbol, settings, version)
    candles = validate_candles(candles, utcnow(), instrument.market)
    features = build_features(candles)
    # Never report a test return on the model-fitting, calibration, or threshold-tuning rows.
    available = features.loc[features.index > pd.Timestamp(metadata["split"]["validation_end"])]
    if len(available) < 2:
        raise ModelError("No out-of-sample candles after validation end; collect new history")
    probability = pd.Series(_calibrated(booster.predict(available), calibration), index=available.index)
    expected = _expected(probability, metadata["positive_mean"], metadata["negative_mean"])
    report, benchmarks = _evaluation(candles, instrument, probability, expected, metadata["threshold"],
                                     available.index[0], available.index[-1], settings)
    report.update({"model_version": metadata["version"], "benchmarks": benchmarks,
                   "period": {"start": available.index[0].isoformat(), "end": available.index[-1].isoformat()},
                   "out_of_sample": True, "previously_used_for_acceptance": available.index[0] <= pd.Timestamp(metadata["split"]["test_end"])})
    return report
