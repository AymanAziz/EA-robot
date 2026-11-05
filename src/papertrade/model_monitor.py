"""Matured forecast diagnostics, separate from deployment and trading permissions.

This measures directional forecasts against observed prices. Gross forward returns
are NOT executed trade returns, and these diagnostics never claim profitability.
"""
from __future__ import annotations

import json
import math
from collections import Counter
from datetime import datetime

import numpy as np
import pandas as pd
from sqlalchemy import select

from papertrade.data import DataError, validate_candles
from papertrade.db import Database, aware
from papertrade.domain import INSTRUMENTS
from papertrade.ml import make_labels
from papertrade.models import ModelVersion, PredictionRow

MIN_OBSERVATIONS = 30
MAX_OBSERVATIONS_PER_MODEL = 500
BRIER_DRIFT_TOLERANCE = .05


def _timestamp(value):
    if value is None:
        return None
    try:
        stamp = pd.Timestamp(value)
        return stamp.tz_convert("UTC") if stamp.tzinfo is not None else None
    except (ValueError, TypeError):
        return None


def _cutoff(metadata):
    split = metadata.get("split", {})
    split = split if isinstance(split, dict) else {}
    candidates = [metadata.get("data_end")] + [split.get(name) for name in
        ("train_end", "calibration_end", "validation_end", "test_end")]
    stamps = [stamp for stamp in (_timestamp(value) for value in candidates if value is not None) if stamp is not None]
    return max(stamps) if stamps else None


def _reference(metadata):
    metadata = metadata if isinstance(metadata, dict) else {}
    scores = metadata.get("classification", {})
    scores = scores if isinstance(scores, dict) else {}
    for field in ("brier", "class_prior_brier"):
        value = scores.get(field)
        if isinstance(value, (int, float)) and math.isfinite(value) and 0 <= value <= 1:
            return float(value), f"recorded_{field}"
    # A declared neutral probability of .5 has squared error .25 for either
    # binary label. This is a fixed benchmark, not a fabricated model score.
    return .25, "neutral_0.5_probability"


def monitor_predictions(db: Database, symbol: str, candles: pd.DataFrame, now: datetime) -> dict:
    """Score up to500 recent, genuinely recorded out-of-sample forecasts per model.

    A label needs the next open through the open four bars after entry; all these
    observations must be from completed, validated candles. Training/evaluation
    history, forecasts recorded after the outcome, unknown model metadata, invalid
    probabilities and missing future horizons are excluded. Callers supply the
    available observation window; repeated calls do not accumulate duplicated scores.
    """
    if symbol not in INSTRUMENTS or now.tzinfo is None:
        raise ValueError("Supported symbol and timezone-aware evaluation time required")
    result = {"symbol": symbol, "evaluated_at": aware(now).isoformat(), "models": {},
              "status": "warming_up", "excluded": {}, "minimum_observations": MIN_OBSERVATIONS,
              "maximum_observations_per_model": MAX_OBSERVATIONS_PER_MODEL,
              "interpretation": "forecast diagnostics; gross forward returns are not trade P/L"}
    try:
        frame = validate_candles(candles, now, INSTRUMENTS[symbol].market)
    except DataError:
        result.update(status="error", reason="market_data_invalid_or_unavailable")
        db.health(f"model_performance:{symbol}", result["status"], json.dumps(result, allow_nan=False), now)
        return result
    result["data_timestamp"] = frame.index[-1].isoformat()
    result["window_start"] = frame.index[0].isoformat()
    labels = make_labels(frame, horizon=4)
    with db.session() as session:
        versions = {row.version: row for row in session.scalars(select(ModelVersion).where(ModelVersion.symbol == symbol))}
        rows = session.scalars(select(PredictionRow).where(
            PredictionRow.symbol == symbol,
            PredictionRow.candle_at >= frame.index[0].to_pydatetime(),
            PredictionRow.candle_at <= frame.index[-1].to_pydatetime(),
        ).order_by(PredictionRow.candle_at, PredictionRow.id)).all()
    excluded = Counter()
    observations = {}
    for prediction in rows:
        version = versions.get(prediction.model_version)
        if version is None:
            excluded["model_metadata_missing"] += 1
            continue
        observations.setdefault(prediction.model_version, [])
        metadata = version.metrics if isinstance(version.metrics, dict) else {}
        trained_at = _timestamp(metadata.get("trained_at"))
        cutoff = _cutoff(metadata)
        stamp = pd.Timestamp(aware(prediction.candle_at))
        created_at = pd.Timestamp(aware(prediction.created_at))
        if trained_at is None or cutoff is None:
            excluded["model_training_period_unknown"] += 1
            continue
        if stamp <= cutoff or created_at < trained_at:
            excluded["training_or_evaluation_period"] += 1
            continue
        if created_at < stamp + pd.Timedelta(minutes=15) or created_at > pd.Timestamp(now):
            excluded["prediction_recording_time_invalid"] += 1
            continue
        if created_at >= stamp + pd.Timedelta(minutes=75):
            excluded["prediction_recorded_after_outcome"] += 1
            continue
        probability = prediction.probability
        if not math.isfinite(probability) or not 0 <= probability <= 1:
            excluded["invalid_probability"] += 1
            continue
        if stamp not in labels.index:
            excluded["outcome_not_mature_or_missing"] += 1
            continue
        outcome = labels.loc[stamp]
        observations[prediction.model_version].append((float(probability), int(outcome.label),
                                                       float(outcome.gross_return), stamp))
    mature_statuses = []
    for version, values in observations.items():
        values = values[-MAX_OBSERVATIONS_PER_MODEL:]
        reference, reference_source = _reference(versions[version].metrics)
        score = {"count": len(values), "reference_brier": reference, "reference_source": reference_source,
                 "active": versions[version].active, "status": "warming_up", "brier": None,
                 "accuracy": None, "mean_gross_forward_return": None}
        if values:
            probabilities = np.array([value[0] for value in values])
            truth = np.array([value[1] for value in values])
            squared_errors = (probabilities - truth) ** 2
            brier = float(squared_errors.mean())
            score.update(brier=brier, accuracy=float(np.mean((probabilities >= .5) == truth)),
                         mean_gross_forward_return=float(np.mean([value[2] for value in values])),
                         first_prediction=values[0][3].isoformat(), last_prediction=values[-1][3].isoformat())
            if len(values) >= MIN_OBSERVATIONS:
                standard_error = float(squared_errors.std(ddof=1) / math.sqrt(len(values)))
                lower = max(0., brier - 1.96 * standard_error)
                score["brier_lower_95_approx"] = lower
                score["status"] = "degraded" if brier > reference + BRIER_DRIFT_TOLERANCE and lower > reference else "ok"
                mature_statuses.append(score["status"])
        result["models"][version] = score
    if "degraded" in mature_statuses:
        result["status"] = "degraded"
    elif mature_statuses:
        result["status"] = "ok"
    result["excluded"] = dict(excluded)
    result["diagnostic_criteria"] = {"brier_drift_tolerance": BRIER_DRIFT_TOLERANCE,
        "confidence": "approximate normal bound; overlapping forward labels are dependent",
        "action": "diagnostic only; no automatic activation, deactivation or order"}
    db.health(f"model_performance:{symbol}", result["status"], json.dumps(result, sort_keys=True, allow_nan=False), now)
    return result
