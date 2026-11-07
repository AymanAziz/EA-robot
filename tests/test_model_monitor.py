"""Model monitoring scores recorded forecasts; fixtures are explicitly artificial."""
import json
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from papertrade.model_monitor import monitor_predictions
from papertrade.models import Health, ModelVersion, PredictionRow


START = datetime(2025, 1, 1, tzinfo=timezone.utc)


def history(count=80, down=False):
    index = pd.date_range(START, periods=count, freq="15min")
    opened = pd.Series([100 - i * .2 if down else 100 + i * .2 for i in range(count)], index=index)
    return pd.DataFrame({"open": opened, "close": opened, "high": opened + .1,
                         "low": opened - .1, "volume": 1000.}, index=index)


def record_model(db, version="v1", reference=.1, horizon=4):
    with db.session() as session:
        session.add(ModelVersion(symbol="BTC/USD", version=version, accepted=True, active=True,
            created_at=START - timedelta(days=1), metrics={
                "trained_at": (START - timedelta(days=1)).isoformat(),
                "data_end": (START - timedelta(days=1, hours=1)).isoformat(),
                "horizon": horizon,
                "classification": {"brier": reference}}))


def record_predictions(db, count=35, probability=.9, version="v1", created_after_outcome=False):
    with db.session() as session:
        for i in range(count):
            candle = START + timedelta(minutes=15 * i)
            session.add(PredictionRow(symbol="BTC/USD", candle_at=candle, model_version=version,
                probability=probability, expected_return=.001, regime="range",
                created_at=candle + timedelta(minutes=90 if created_after_outcome else 15, seconds=20)))


def test_matured_predictions_have_independently_known_brier_and_accuracy(db):
    record_model(db)
    record_predictions(db)
    result = monitor_predictions(db, "BTC/USD", history(), START + timedelta(days=1))
    score = result["models"]["v1"]
    assert score["count"] == 35
    assert score["brier"] == pytest.approx(.01)
    assert score["accuracy"] == 1
    assert result["status"] == "ok"
    with db.session() as session:
        health = session.get(Health, "model_performance:BTC/USD")
        assert json.loads(health.detail)["models"]["v1"]["count"] == 35


def test_missing_future_candles_and_incomplete_outcomes_are_not_scored(db):
    record_model(db)
    record_predictions(db, count=20)
    frame = history(20)
    # At this instant the final raw candle is incomplete. Only19 candles are
    # available, and5 more future opening observations are needed per label.
    result = monitor_predictions(db, "BTC/USD", frame, frame.index[-1].to_pydatetime())
    assert result["models"]["v1"]["count"] == 14
    assert result["status"] == "warming_up"


def test_prediction_matures_only_after_its_recorded_model_horizon(db):
    record_model(db, horizon=48)
    record_predictions(db, count=1)
    frame = history(40)

    result = monitor_predictions(db, "BTC/USD", frame, frame.index[-1].to_pydatetime() + timedelta(minutes=15))

    assert result["models"]["v1"]["count"] == 0
    assert result["excluded"]["outcome_not_mature_or_missing"] == 1


def test_bad_recent_performance_is_diagnostic_only_after_minimum_count(db):
    record_model(db)
    record_predictions(db, count=29)
    frame = history(down=True)
    result = monitor_predictions(db, "BTC/USD", frame, START + timedelta(days=1))
    assert result["status"] == "warming_up"
    with db.session() as session:
        session.add(PredictionRow(symbol="BTC/USD", candle_at=START + timedelta(minutes=15 * 29),
            model_version="v1", probability=.9, expected_return=.001, regime="range",
            created_at=START + timedelta(minutes=15 * 30, seconds=20)))
    result = monitor_predictions(db, "BTC/USD", frame, START + timedelta(days=1))
    assert result["status"] == "degraded"
    assert result["models"]["v1"]["brier"] == pytest.approx(.81)
    with db.session() as session:
        model = session.get(ModelVersion, 1)
        assert model.active and model.accepted  # Diagnostics do not mutate deployment gates.


def test_hindsight_or_training_period_predictions_are_excluded(db):
    record_model(db)
    record_predictions(db, count=35, created_after_outcome=True)
    result = monitor_predictions(db, "BTC/USD", history(), START + timedelta(days=1))
    assert result["models"]["v1"]["count"] == 0
    assert result["excluded"]["prediction_recorded_after_outcome"] == 35


def test_unknown_model_reference_is_reported_without_invented_metrics(db):
    record_predictions(db, version="unknown")
    result = monitor_predictions(db, "BTC/USD", history(), START + timedelta(days=1))
    assert result["status"] == "warming_up"
    assert result["models"] == {}
    assert result["excluded"]["model_metadata_missing"] == 35


def test_models_are_scored_separately_and_duplicate_calls_do_not_accumulate(db):
    record_model(db)
    record_model(db, version="v2")
    record_predictions(db, version="v1")
    record_predictions(db, version="v2", probability=.2)
    first = monitor_predictions(db, "BTC/USD", history(), START + timedelta(days=1))
    second = monitor_predictions(db, "BTC/USD", history(), START + timedelta(days=1))
    assert first == second
    assert first["models"]["v1"]["count"] == 35
    assert first["models"]["v2"]["brier"] == pytest.approx(.64)


def test_training_and_acceptance_sample_cannot_masquerade_as_online_performance(db):
    record_model(db)
    record_predictions(db)
    with db.session() as session:
        row = session.get(ModelVersion, 1)
        row.metrics = row.metrics | {"data_end": (START + timedelta(minutes=15 * 20)).isoformat()}
    result = monitor_predictions(db, "BTC/USD", history(), START + timedelta(days=1))
    assert result["models"]["v1"]["count"] == 14
    assert result["excluded"]["training_or_evaluation_period"] == 21


def test_invalid_outcome_history_records_error_without_invented_scores(db):
    record_model(db)
    record_predictions(db)
    frame = history().drop(history().index[20])
    result = monitor_predictions(db, "BTC/USD", frame, START + timedelta(days=1))
    assert result["status"] == "error"
    assert result["models"] == {}
    with db.session() as session:
        assert session.get(Health, "model_performance:BTC/USD").status == "error"
