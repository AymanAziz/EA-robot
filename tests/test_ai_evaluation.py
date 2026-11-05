import pandas as pd
import pytest

from papertrade.ai.evaluation import approve_certificate, build_certificate, evaluate_strategies
from papertrade.domain import INSTRUMENTS


def history(n=220):
    return pd.DataFrame({"open": 100., "high": 100.1, "low": 99.9, "close": 100., "volume": 100000.},
                        index=pd.date_range("2026-01-01", periods=n, freq="15min", tz="UTC"))


def observations(frame, *, recommendation="BUY"):
    result = []
    for stamp in frame.index[55:-6]:
        close = stamp + pd.Timedelta(minutes=15)
        result.append(dict(symbol="BTC/USD", candle_at=stamp.isoformat(),
            decision_at=(close + pd.Timedelta(seconds=20)).isoformat(), quant_model_version="quant-v1",
            quant_data_end=frame.index[40].isoformat(), quant_trained_at=frame.index[45].isoformat(),
            quant_model_accepted=True, quant_threshold=.6, execution_venue="local_simulator", probability=.9, expected_return=.02,
            ai_provider="groq", ai_model="configured-model", source="forward_observation",
            ai_created_at=(close - pd.Timedelta(minutes=14, seconds=50)).isoformat(),
            ai_response=dict(symbol="BTC/USD", recommendation=recommendation, direction_bias="long",
                             market_regime="ranging", risk_level="medium", confidence=.8,
                             data_timestamp=(close - pd.Timedelta(minutes=15)).isoformat())))
    return result


def test_replay_uses_observed_ai_veto_and_never_reports_it_as_broker_fills(settings):
    frame = history()
    report = evaluate_strategies(frame, observations(frame, recommendation="NO_TRADE"), INSTRUMENTS["BTC/USD"], settings)
    assert report["source"] == "forward_replay"
    assert report["strategies"]["quant_only"]["test"]["metrics"]["trade_count"] > 0
    assert report["strategies"]["ai_filtered_quant"]["test"]["metrics"]["trade_count"] == 0
    assert not report["strategies"]["ai_filtered_quant"]["accepted"]
    assert report["strategies"]["ai_only_research"]["metrics"] is None


def test_replay_excludes_hindsight_training_samples_and_unmatured_observations(settings):
    frame = history()
    data = observations(frame)
    data[0]["quant_data_end"] = frame.index[-1].isoformat()
    data[1]["ai_created_at"] = (pd.Timestamp(data[1]["decision_at"]) + pd.Timedelta(hours=1)).isoformat()
    data[2]["source"] = "hypothetical"
    report = evaluate_strategies(frame, data, INSTRUMENTS["BTC/USD"], settings)
    assert report["excluded"]["training_or_missing_quant_provenance"] == 1
    assert report["excluded"]["source_not_forward_observation"] == 1
    # A late AI record remains a real quant observation but cannot authorize an AI entry.
    assert report["ai_usable_observations"]["ai_filtered_quant"] < report["observations"]


def test_missing_ai_does_not_delete_quant_benchmark_observations(settings):
    frame = history()
    data = observations(frame)
    for item in data:
        item["ai_response"] = None
    report = evaluate_strategies(frame, data, INSTRUMENTS["BTC/USD"], settings)
    assert report["observations"] == len(data)
    assert report["strategies"]["quant_only"]["test"]["metrics"]["trade_count"] > 0
    assert report["strategies"]["ai_filtered_quant"]["test"]["metrics"]["trade_count"] == 0


def test_replay_is_reproducible_and_preserves_expected_return_exit(settings):
    frame = history()
    data = observations(frame)
    for item in data[10:]:
        item["expected_return"] = -.02
        item["ai_response"]["recommendation"] = "NO_TRADE"
    first = evaluate_strategies(frame, data, INSTRUMENTS["BTC/USD"], settings)
    assert first == evaluate_strategies(frame, data, INSTRUMENTS["BTC/USD"], settings)
    quant_trades = first["strategies"]["quant_only"]["validation"]["trades"]
    ai_trades = first["strategies"]["ai_filtered_quant"]["validation"]["trades"]
    assert quant_trades and ai_trades
    assert quant_trades[0]["exit_time"] == ai_trades[0]["exit_time"]


def test_mixed_quant_models_and_duplicate_observations_are_not_silently_selected(settings):
    frame = history()
    data = observations(frame)
    data[-1]["quant_model_version"] = "different-model"
    with pytest.raises(ValueError, match="one quantitative model"):
        evaluate_strategies(frame, data, INSTRUMENTS["BTC/USD"], settings)
    data = observations(frame)
    data.append(data[0])
    with pytest.raises(ValueError, match="Duplicate"):
        evaluate_strategies(frame, data, INSTRUMENTS["BTC/USD"], settings)


def test_failed_candidate_is_never_approved_and_report_cannot_change_bindings(settings):
    frame = history()
    report = evaluate_strategies(frame, observations(frame), INSTRUMENTS["BTC/USD"], settings)
    candidate = build_certificate(report, "ai_filtered_quant", "quant-v1", "groq", "configured-model", settings)
    assert not candidate["approved"] and not candidate["accepted"]
    with pytest.raises(ValueError, match="did not pass"):
        approve_certificate(candidate)
    with pytest.raises(ValueError, match="provenance"):
        build_certificate(report, "ai_filtered_quant", "different-quant", "groq", "configured-model", settings)
    altered = dict(candidate, accepted=True)
    with pytest.raises(ValueError, match="integrity"):
        approve_certificate(altered)


def test_ai_arriving_after_the_modeled_fill_never_receives_historical_entry_credit(settings):
    frame = history()
    data = observations(frame)
    for item in data:
        close = pd.Timestamp(item["candle_at"]) + pd.Timedelta(minutes=15)
        item["ai_response"]["data_timestamp"] = close.isoformat()
        item["ai_created_at"] = (close + pd.Timedelta(seconds=10)).isoformat()
    report = evaluate_strategies(frame, data, INSTRUMENTS["BTC/USD"], settings)
    assert report["strategies"]["quant_only"]["test"]["metrics"]["trade_count"] > 0
    assert report["strategies"]["ai_filtered_quant"]["test"]["metrics"]["trade_count"] == 0


def test_exact_frozen_quant_threshold_is_used_instead_of_a_new_default(settings):
    frame = history()
    data = observations(frame)
    for item in data:
        item["quant_threshold"] = .95
    report = evaluate_strategies(frame, data, INSTRUMENTS["BTC/USD"], settings)
    assert report["quant_threshold"] == .95
    assert report["strategies"]["quant_only"]["test"]["metrics"]["trade_count"] == 0


def test_different_execution_venues_and_models_trained_later_are_excluded(settings):
    frame = history()
    data = observations(frame)
    data[0]["execution_venue"] = "broker_paper"
    data[1]["quant_trained_at"] = frame.index[-1].isoformat()
    report = evaluate_strategies(frame, data, INSTRUMENTS["BTC/USD"], settings)
    assert report["excluded"]["different_or_missing_execution_venue"] == 1
    assert report["excluded"]["training_or_missing_quant_provenance"] == 1
