"""Persisted cloud-analysis seam with real SQLite and mocked provider HTTP only."""
from datetime import datetime, timedelta, timezone
import json

import httpx
import pandas as pd
from pydantic import SecretStr
import pytest
from sqlalchemy import select

from papertrade.ai.budget import UsageBudget
from papertrade.ai.service import AIDisabled, AIService, build_context, make_provider
from papertrade.models import AIAnalysisRow, AIRequest, PredictionRow


NOW = datetime(2026, 11, 5, 12, 0, 20, tzinfo=timezone.utc)


@pytest.fixture
def evidence(settings, db):
    settings.ai_enabled = True
    settings.ai_account_tier = "free"
    settings.groq_api_key = SecretStr("fixture-secret-key")
    settings.groq_model = "fixture-model"
    index = pd.date_range(end=NOW.replace(second=0)-timedelta(minutes=15), periods=130, freq="15min")
    close = pd.Series([100 + number * .01 for number in range(len(index))], index=index)
    candles = pd.DataFrame({"open": close-.01, "high": close+.1, "low": close-.1,
                            "close": close, "volume": 50.0}, index=index)
    db.store_candles("BTC/USD", candles, "explicit-artificial-test-fixture")
    with db.session() as session:
        session.add(PredictionRow(symbol="BTC/USD", candle_at=index[-1].to_pydatetime(),
            model_version="fixture-quant-v1", probability=.7, expected_return=.02, regime="uptrend"))
    return candles


def provider_transport(calls, *, invalid=False, unavailable=False):
    def respond(request):
        calls.append(request)
        if request.method == "GET":
            return httpx.Response(200, json={"data": [{"id": "fixture-model"}]})
        if unavailable:
            return httpx.Response(503, json={"private": "must never reach storage or logs"})
        payload = json.loads(request.content)
        context = json.loads(payload["messages"][-1]["content"])
        analysis = {"symbol": context["symbol"], "market_regime": "bullish", "direction_bias": "long",
            "recommendation": "BUY", "confidence": 2.0 if invalid else .7, "risk_level": "medium",
            "reasoning_summary": "Momentum agrees with the supplied quantitative trend evidence.",
            "supporting_factors": ["Trend confirmation"], "risk_factors": ["No verified news context was provided"],
            "data_timestamp": context["data_timestamp"]}
        return httpx.Response(200, json={"model": "fixture-model", "choices": [{"finish_reason": "stop",
            "message": {"role": "assistant", "content": json.dumps(analysis)}}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 80, "total_tokens": 180}})
    return httpx.MockTransport(respond)


def service(settings, db, calls, clock, **transport_options):
    transport = provider_transport(calls, **transport_options)
    def factory(cfg, budget, symbol):
        provider = make_provider(cfg, budget, symbol, transport=transport)
        provider.sleep = lambda _: None
        return provider
    return AIService(settings, db, provider_factory=factory, clock=lambda: clock[0])


def test_worker_uses_actual_stored_completed_evidence_and_no_external_news(settings, db, evidence):
    context = build_context(db, "BTC/USD", now=NOW)
    assert context.current_price == pytest.approx(101.29)
    assert context.data_timestamp == NOW.replace(second=0)
    assert len(context.recent_candles) == settings.ai_recent_candles
    assert context.recent_candles[-1].timestamp + timedelta(minutes=15) == context.data_timestamp
    assert context.news_context == "No verified news context provided"
    assert context.macro_context == "No verified macroeconomic context provided"
    assert context.quant_prediction.model_version == "fixture-quant-v1"


def test_valid_analysis_persists_and_restart_cache_avoids_another_provider_call(settings, db, evidence):
    calls, clock = [], [NOW]
    first = service(settings, db, calls, clock)
    assert first.analyze("BTC/USD")["status"] == "valid"
    assert len(calls) == 2
    restarted = service(settings, db, calls, clock)
    cached = restarted.cached("BTC/USD")
    assert cached is not None and cached.response["recommendation"] == "BUY"
    assert restarted.analyze("BTC/USD")["status"] == "cached"
    assert len(calls) == 2
    assert UsageBudget(db, lambda: NOW).metrics()["tokens_reported"] == 180
    with db.session() as session:
        assert len(session.scalars(select(AIAnalysisRow)).all()) == 1


def test_material_state_invalidation_does_not_reuse_an_old_quantitative_model(settings, db, evidence):
    calls, clock = [], [NOW]
    worker = service(settings, db, calls, clock)
    worker.analyze("BTC/USD")
    with db.session() as session:
        row = session.scalar(select(PredictionRow))
        row.model_version = "fixture-quant-v2"
    assert worker.cached("BTC/USD") is None
    # Material events still honor the minimum inter-request interval.
    assert worker.analyze("BTC/USD")["status"] == "waiting"
    assert len(calls) == 2


def test_probability_event_can_refresh_after_minimum_interval(settings, db, evidence):
    calls, clock = [], [NOW]
    worker = service(settings, db, calls, clock)
    worker.analyze("BTC/USD")
    clock[0] += timedelta(minutes=15)
    latest = evidence.index[-1] + pd.Timedelta(minutes=15)
    update = pd.DataFrame({"open": [101.29], "high": [101.5], "low": [101.2], "close": [101.3], "volume": [50.0]}, index=pd.DatetimeIndex([latest]))
    db.store_candles("BTC/USD", update, "explicit-artificial-test-fixture")
    with db.session() as session:
        session.add(PredictionRow(symbol="BTC/USD", candle_at=latest.to_pydatetime(),
            model_version="fixture-quant-v1", probability=.85, expected_return=.02, regime="uptrend"))
    assert worker.cached("BTC/USD") is None
    assert worker.analyze("BTC/USD")["status"] == "valid"
    assert len(calls) == 4


def test_unchanged_state_can_reuse_previous_candle_analysis_within_freshness(settings, db, evidence):
    calls, clock = [], [NOW]
    worker = service(settings, db, calls, clock)
    worker.analyze("BTC/USD")
    original = build_context(db, "BTC/USD", now=NOW)
    clock[0] += timedelta(minutes=30)
    # Cached opinions are validated against their original context, not forged new timestamps.
    cached = worker.cached("BTC/USD", context=original)
    assert cached is not None
    assert datetime.fromisoformat(cached.response["data_timestamp"].replace("Z", "+00:00")) == original.data_timestamp
    assert len(calls) == 2


def test_expired_or_tampered_analysis_is_not_reused(settings, db, evidence):
    calls, clock = [], [NOW]
    worker = service(settings, db, calls, clock)
    worker.analyze("BTC/USD")
    context = build_context(db, "BTC/USD", now=NOW)
    with db.session() as session:
        row = session.scalar(select(AIAnalysisRow))
        row.context = dict(row.context) | {"current_price": 50000.0}
    assert worker.cached("BTC/USD", context=context) is None
    clock[0] += timedelta(hours=2)
    assert worker.cached("BTC/USD", context=context) is None


def test_invalid_provider_output_is_persisted_as_error_without_fabricated_analysis(settings, db, evidence):
    calls, clock = [], [NOW]
    worker = service(settings, db, calls, clock, invalid=True)
    result = worker.analyze("BTC/USD")
    assert result["status"] == "error" and worker.cached("BTC/USD") is None
    with db.session() as session:
        row = session.scalar(select(AIAnalysisRow))
        assert row.status == "error" and row.response is None
        assert "fixture-secret-key" not in row.error
        assert len(session.scalars(select(AIRequest)).all()) == 2


def test_provider_outage_is_bounded_and_cannot_invent_a_fallback(settings, db, evidence):
    calls, clock = [], [NOW]
    worker = service(settings, db, calls, clock, unavailable=True)
    assert worker.analyze("BTC/USD")["status"] == "error"
    assert len(calls) == 3  # Discovery + two bounded inference attempts.
    assert all(request.url.host == "api.groq.com" for request in calls)
    assert worker.cached("BTC/USD") is None


@pytest.mark.parametrize("changes", [
    {"ai_account_tier": "unverified"}, {"ai_account_tier": "paid", "ai_allow_paid": False},
    {"groq_api_key": SecretStr("")}, {"ai_provider": "none"},
    {"ai_provider": "hermes", "hermes_api_key": SecretStr("fixture-key"), "ai_allow_paid": False},
])
def test_unauthorized_or_missing_ai_access_does_not_send_requests(settings, db, evidence, changes):
    for key, value in changes.items():
        setattr(settings, key, value)
    with pytest.raises(AIDisabled):
        make_provider(settings, UsageBudget(db, lambda: NOW), "BTC/USD")
    assert UsageBudget(db, lambda: NOW).metrics()["requests"] == 0


def test_catalog_discovery_can_precede_enabling_analysis_and_model_selection(settings, db):
    settings.ai_enabled = False
    settings.ai_account_tier = "free"
    settings.groq_api_key = SecretStr("fixture-key")
    settings.groq_model = ""
    calls = []
    provider = make_provider(settings, UsageBudget(db, lambda: NOW), discovery=True,
                             transport=provider_transport(calls))
    assert provider.get_models()[0]["id"] == "fixture-model"
    assert len(calls) == 1


@pytest.mark.parametrize("changes", [
    {"ai_account_tier": "unverified"},
    {"ai_account_tier": "paid", "ai_allow_paid": False},
    {"groq_api_key": SecretStr("")},
])
def test_revoking_provider_access_invalidates_prior_cached_analysis(settings, db, evidence, changes):
    calls, clock = [], [NOW]
    worker = service(settings, db, calls, clock)
    assert worker.analyze("BTC/USD")["status"] == "valid"
    for key, value in changes.items():
        setattr(settings, key, value)
    assert worker.cached("BTC/USD") is None
    assert len(calls) == 2


def test_disabled_worker_does_not_read_market_or_broker_data(settings, db):
    settings.ai_enabled = False
    worker = AIService(settings, db, clock=lambda: NOW)
    assert worker.run_once()["status"] == "disabled"
    assert UsageBudget(db, lambda: NOW).metrics()["requests"] == 0
