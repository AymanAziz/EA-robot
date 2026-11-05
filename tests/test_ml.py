from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from papertrade.config import Settings
from papertrade.domain import INSTRUMENTS
from papertrade.features import build_features
from papertrade.ml import ModelError, make_labels, predict, promote_model, train_model


def synthetic_history(n=1600):
    """Deterministic artificial research fixture; never submitted to an external provider."""
    rng = np.random.default_rng(412)
    returns = rng.normal(0.00002, 0.003, n)
    close = 100 * np.exp(np.cumsum(returns))
    opened = np.r_[100, close[:-1]]
    return pd.DataFrame({"open": opened, "close": close,
                         "high": np.maximum(opened, close) + 0.2,
                         "low": np.minimum(opened, close) - 0.2,
                         "volume": rng.uniform(100, 200, n)},
                        index=pd.date_range("2025-01-01", periods=n, freq="15min", tz="UTC"))


def test_appending_future_prices_cannot_change_historical_features():
    frame = synthetic_history()
    pd.testing.assert_frame_equal(build_features(frame.iloc[:200]), build_features(frame).iloc[:151])


def test_feature_atr_uses_true_range_and_flat_rsi_is_neutral():
    frame = synthetic_history(100)
    frame.loc[:, ["open", "close"]] = 100.
    frame.loc[:, "high"] = 102.
    frame.loc[:, "low"] = 99.
    row = build_features(frame).iloc[-1]
    assert row.atr == pytest.approx(3.)
    assert row.rsi14 == pytest.approx(50.)


def test_label_uses_next_open_and_never_last_unknown_candles():
    frame = synthetic_history(100)
    labels = make_labels(frame, horizon=4)
    stamp = frame.index[20]
    assert labels.loc[stamp, "gross_return"] == pytest.approx(frame.open.iloc[25] / frame.open.iloc[21] - 1)
    assert labels.index[-1] == frame.index[-6]


def test_missing_model_disables_prediction(tmp_path):
    with pytest.raises(ModelError, match="active model"):
        predict(synthetic_history(), INSTRUMENTS["BTC/USD"], Settings(models_dir=tmp_path))


def test_genuine_lightgbm_candidate_requires_explicit_validation_before_activation(tmp_path):
    settings = Settings(models_dir=tmp_path)
    frame = synthetic_history()
    metadata = train_model(frame, INSTRUMENTS["BTC/USD"], settings,
                           now=datetime(2025, 1, 20, tzinfo=timezone.utc), params={"n_estimators": 20})
    assert metadata["algorithm"] == "LightGBM"
    assert len(metadata["walk_forward"]) == 3
    assert metadata["split"]["train_end"] < metadata["split"]["calibration_start"]
    assert metadata["split"]["calibration_end"] < metadata["split"]["validation_start"]
    assert metadata["split"]["validation_end"] < metadata["split"]["test_start"]
    assert not (tmp_path / "BTC_USD" / "active.json").exists()
    assert (tmp_path / "BTC_USD" / metadata["version"] / "booster.txt").read_text().startswith("tree")
    artifact = tmp_path / "BTC_USD" / metadata["version"] / "booster.txt"
    before = artifact.stat().st_mtime_ns
    repeated = train_model(frame, INSTRUMENTS["BTC/USD"], settings,
                            now=datetime(2025, 1, 21, tzinfo=timezone.utc), params={"n_estimators": 20})
    assert repeated["version"] == metadata["version"]
    assert repeated["trained_at"] == metadata["trained_at"]
    assert artifact.stat().st_mtime_ns == before
    if not metadata["accepted"]:
        with pytest.raises(ModelError, match="validation"):
            promote_model("BTC/USD", metadata["version"], settings)


def test_tampered_artifact_cannot_be_promoted(tmp_path):
    settings = Settings(models_dir=tmp_path)
    metadata = train_model(synthetic_history(), INSTRUMENTS["BTC/USD"], settings,
                           now=datetime(2025, 1, 20, tzinfo=timezone.utc), params={"n_estimators": 10})
    path = tmp_path / "BTC_USD" / metadata["version"] / "booster.txt"
    path.write_text("tampered")
    with pytest.raises(ModelError):
        promote_model("BTC/USD", metadata["version"], settings)


def test_cannot_sneak_in_future_unknown_labels():
    labels = make_labels(synthetic_history(100))
    assert labels["gross_return"].notna().all()
    assert set(labels.label.unique()) <= {0, 1}


def test_validated_native_lightgbm_can_be_promoted_and_inferred_but_expires(tmp_path):
    """Artificial predictable cycle tests the success path, not a market-performance claim."""
    from papertrade.domain import utcnow
    count = 2400
    now = pd.Timestamp(utcnow()).floor("15min") + pd.Timedelta(seconds=20)
    index = pd.date_range(now.floor("15min") - pd.Timedelta(minutes=15 * count), periods=count, freq="15min", tz="UTC")
    movement = np.where(np.arange(count) % 16 < 8, .01, -.01)
    close = 100 * np.exp(np.cumsum(movement))
    opened = np.r_[100, close[:-1]]
    frame = pd.DataFrame({"open": opened, "close": close, "high": np.maximum(opened, close) + .1,
                         "low": np.minimum(opened, close) - .1, "volume": 10000.}, index=index)
    settings = Settings(models_dir=tmp_path)
    candidate = train_model(frame, INSTRUMENTS["BTC/USD"], settings, now=now.to_pydatetime(), params={"n_estimators": 30})
    assert candidate["accepted"], candidate["validation_failures"]
    promote_model("BTC/USD", candidate["version"], settings)
    prediction = predict(frame, INSTRUMENTS["BTC/USD"], settings, now=now.to_pydatetime())
    assert 0 <= prediction.probability <= 1
    assert prediction.model_version == candidate["version"]
    assert prediction.atr > 0
    assert prediction.expected_return != 0
    changed_policy = settings.model_copy(update={"min_net_edge_bps": settings.min_net_edge_bps + 1})
    with pytest.raises(ModelError, match="policy changed"):
        predict(frame, INSTRUMENTS["BTC/USD"], changed_policy, now=now.to_pydatetime())
    from dataclasses import replace
    changed_cost = replace(INSTRUMENTS["BTC/USD"], fee_bps=30)
    with pytest.raises(ModelError, match="policy changed"):
        predict(frame, changed_cost, settings, now=now.to_pydatetime())
    with pytest.raises(ModelError, match="outdated"):
        predict(frame, INSTRUMENTS["BTC/USD"], settings, now=(now + pd.Timedelta(days=31)).to_pydatetime())
