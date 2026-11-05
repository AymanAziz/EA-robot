from datetime import datetime, timedelta, timezone

import pytest

from papertrade.decisions import Decision
from papertrade.ai.fusion import fuse_decision, seal_certificate, strategy_policy

NOW = datetime(2026, 11, 5, 12, 0, 20, tzinfo=timezone.utc)
CANDLE = NOW.replace(hour=11, minute=45, second=0)


def analysis(**updates):
    return dict(symbol="BTC/USD", recommendation="BUY", direction_bias="long", market_regime="bullish",
                risk_level="low", confidence=.72, data_timestamp=(CANDLE + timedelta(minutes=15)).isoformat(),
                reasoning_summary="Trend agrees", supporting_factors=["Momentum"], risk_factors=[]) | updates


def certificate(settings, strategy="ai_filtered_quant", **updates):
    value = dict(schema_version=1, strategy=strategy, symbol="BTC/USD", quant_model_version="quant-v1",
                 ai_provider="groq", ai_model="configured-model", policy_sha256=strategy_policy(settings)["sha256"],
                 accepted=True, approved=True, created_at=NOW.isoformat(), approved_at=NOW.isoformat(),
                 expires_at=(NOW + timedelta(days=10)).isoformat(), criteria={"test_fixture": True},
                 source="forward_replay", report_sha256="test-only-report") | updates
    return seal_certificate(value)


def invoke(settings, **updates):
    values = dict(strategy="ai_filtered_quant", symbol="BTC/USD", candle_at=CANDLE, now=NOW,
                  quant_model_version="quant-v1", ai=analysis(), ai_provider="groq", ai_model="configured-model",
                  certificate=certificate(settings), ai_created_at=NOW, settings=settings)
    values.update(updates)
    return fuse_decision(Decision("BUY", "quant_edge", 5), **values)


def enabled(settings):
    return settings.model_copy(update={"strategy_execution_enabled": True})


def test_ai_can_veto_but_cannot_create_an_entry(settings):
    settings = enabled(settings)
    assert invoke(settings).action == "BUY"
    assert invoke(settings, ai=analysis(recommendation="HOLD", direction_bias="neutral")).action == "HOLD"
    values = dict(strategy="ai_filtered_quant", symbol="BTC/USD", candle_at=CANDLE, now=NOW,
                  quant_model_version="quant-v1", ai=analysis(), ai_provider="groq", ai_model="configured-model",
                  certificate=certificate(settings), ai_created_at=NOW, settings=settings)
    assert fuse_decision(Decision("HOLD", "no_quant_edge", 5), **values).action == "HOLD"


def test_missing_or_unapproved_validation_cannot_execute_ai_entries(settings):
    settings = enabled(settings)
    assert invoke(settings, certificate=None).action == "HOLD"
    assert invoke(settings, certificate=certificate(settings, approved=False)).action == "HOLD"
    assert invoke(settings, certificate=certificate(settings, accepted=False)).action == "HOLD"


def test_quant_only_requires_explicit_execution_opt_in(settings):
    assert invoke(settings.model_copy(update={"strategy_execution_enabled": False}), strategy="quant_only").reason == "strategy_execution_disabled"
    assert invoke(enabled(settings), strategy="quant_only").action == "BUY"


def test_ai_confidence_never_overrides_disagreement_or_cost_guard(settings):
    settings = enabled(settings)
    assert invoke(settings, ai=analysis(recommendation="NO_TRADE", confidence=1.)).action == "HOLD"
    assert invoke(settings, ai=analysis(risk_level="high", confidence=1.)).action == "HOLD"


def test_stale_future_unknown_and_contradictory_ai_are_held(settings):
    settings = enabled(settings)
    for changed in [
        {"data_timestamp": (NOW - timedelta(hours=2)).isoformat()},
        {"data_timestamp": (NOW + timedelta(minutes=1)).isoformat()},
        {"symbol": "UNKNOWN"}, {"direction_bias": "short"}, {"market_regime": "bearish"},
    ]:
        assert invoke(settings, ai=analysis(**changed)).action == "HOLD"


def test_hybrid_is_stricter_without_blending_opinion_probabilities(settings):
    settings = enabled(settings)
    cert = certificate(settings, strategy="hybrid")
    assert invoke(settings, strategy="hybrid", certificate=cert).action == "BUY"
    assert invoke(settings, strategy="hybrid", certificate=cert, ai=analysis(risk_level="medium")).action == "HOLD"
    assert invoke(settings, strategy="hybrid", certificate=cert, ai=analysis(market_regime="ranging")).action == "HOLD"


def test_certificate_is_bound_to_exact_policy_model_and_provider(settings):
    settings = enabled(settings)
    assert invoke(settings, ai_model="different-model").action == "HOLD"
    assert invoke(settings, quant_model_version="new-quant-model").action == "HOLD"
    assert invoke(settings, certificate=certificate(settings, expires_at=(NOW - timedelta(seconds=1)).isoformat())).action == "HOLD"
    tampered = certificate(settings)
    tampered["ai_provider"] = "hermes"
    assert invoke(settings, certificate=tampered).action == "HOLD"


def test_research_never_creates_orders_but_all_strategies_preserve_reducing_exits(settings):
    settings = enabled(settings)
    assert invoke(settings, strategy="ai_only_research").action == "HOLD"
    for strategy in ("quant_only", "ai_filtered_quant", "hybrid", "ai_only_research", "invalid"):
        exit_decision = Decision("CLOSE", "risk_reduction", 5)
        assert fuse_decision(exit_decision, strategy=strategy, symbol="BTC/USD", candle_at=CANDLE, now=NOW,
                             quant_model_version="", settings=settings) == exit_decision


@pytest.mark.parametrize("field,value", [
    ("ai_recent_candles", 24), ("ai_event_probability_delta", .2),
    ("ai_event_price_change", .05), ("ai_event_min_interval_minutes", 30),
    ("ai_response_format", "json_schema"), ("ai_max_output_tokens", 1024),
    ("ai_max_attempts", 3), ("ai_timeout_seconds", 15.),
    ("ai_max_daily_requests", 200), ("ai_max_daily_tokens", 200000),
])
def test_cache_prompt_transport_and_budget_changes_invalidate_approved_policy(settings, field, value):
    settings = enabled(settings)
    cert = certificate(settings)
    original = strategy_policy(settings)["sha256"]
    changed = settings.model_copy(update={field: value})
    assert strategy_policy(changed)["sha256"] != original
    assert invoke(changed, certificate=cert).action == "HOLD"
