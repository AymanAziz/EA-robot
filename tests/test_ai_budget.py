"""Durable public budget seam: shared daily limits survive restarts and contention."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from sqlalchemy import select

from papertrade.ai.budget import BudgetExceeded, UsageBudget
from papertrade.ai.providers import AttemptUsage, GroqProvider
from papertrade.models import AIRequest


NOW = datetime(2026, 11, 5, 12, 0, 20, tzinfo=timezone.utc)


def event(total=None, kind="analysis", status="error"):
    return AttemptUsage(status, kind, 200 if status == "success" else None, None,
                        total, 0 if total is not None else None, total, 5.0, {}, total is not None)


def test_reservations_survive_process_restart_and_unknown_outcomes_do_not_refund(settings, db):
    settings.ai_max_daily_tokens = 10
    first = UsageBudget(db, lambda: NOW)
    identifier = first.reserve(7, provider="groq", model="fixture", symbol="BTC/USD")
    restarted = UsageBudget(db, lambda: NOW)
    assert restarted.metrics()["tokens_charged"] == 7
    with pytest.raises(BudgetExceeded):
        restarted.reserve(4, provider="hermes", model="other")
    restarted.finish(identifier, event())
    assert restarted.metrics()["tokens_charged"] == 7
    assert restarted.metrics()["providers"]["groq"]["unknown_usage_requests"] == 1
    # Finishing an already completed request cannot retrospectively refund its reservation.
    restarted.finish(identifier, event(0, status="success"))
    assert restarted.metrics()["tokens_charged"] == 7


def test_known_token_usage_replaces_reservation_and_discovery_counts_requests(settings, db):
    settings.ai_max_daily_requests = 2
    budget = UsageBudget(db, lambda: NOW)
    metadata = budget.reserve(0, provider="groq", model="")
    budget.finish(metadata, event(0, kind="models", status="success"))
    analysis = budget.reserve(1000, provider="groq", model="fixture")
    budget.finish(analysis, event(180, status="success"))
    assert budget.metrics()["requests"] == 2
    assert budget.metrics()["tokens_charged"] == 180
    with pytest.raises(BudgetExceeded):
        budget.reserve(0, provider="groq", model="")


def test_all_providers_share_daily_budget_and_utc_rollover(settings, db):
    settings.ai_max_daily_requests = 1
    clock = [NOW]
    budget = UsageBudget(db, lambda: clock[0])
    budget.reserve(10, provider="groq", model="fixture")
    with pytest.raises(BudgetExceeded):
        budget.reserve(0, provider="hermes", model="alternative")
    clock[0] += timedelta(days=1)
    budget.reserve(0, provider="hermes", model="alternative")
    assert budget.metrics()["requests"] == 1


def test_concurrent_reservations_cannot_overspend_sqlite_budget(settings, db):
    settings.ai_max_daily_requests = 5
    settings.ai_max_daily_tokens = 50
    def reserve(_):
        try:
            return UsageBudget(db, lambda: NOW).reserve(10, provider="groq", model="fixture")
        except BudgetExceeded:
            return None
    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(reserve, range(20)))
    assert len([identifier for identifier in results if identifier is not None]) == 5
    assert UsageBudget(db, lambda: NOW).metrics()["tokens_charged"] == 50


@pytest.mark.parametrize("tokens", [-1, True, 1.5, "100"])
def test_invalid_reservations_cannot_reach_the_ledger(settings, db, tokens):
    with pytest.raises(ValueError):
        UsageBudget(db).reserve(tokens, provider="groq", model="fixture")


def test_retry_requires_another_durable_reservation_before_http(context_for_budget, settings, db):
    settings.ai_max_daily_requests = 2
    requests = []
    def respond(request):
        requests.append(request)
        if request.method == "GET":
            return httpx.Response(200, json={"data": [{"id": "fixture-model"}]})
        return httpx.Response(429)
    before, after = UsageBudget(db, lambda: NOW).callbacks("groq", "fixture-model", "BTC/USD")
    provider = GroqProvider("fixture-key", "fixture-model", transport=httpx.MockTransport(respond),
                            before_attempt=before, after_attempt=after, max_attempts=3, sleep=lambda _: None)
    with pytest.raises(BudgetExceeded):
        provider.analyze_market(context_for_budget, now=NOW)
    assert len(requests) == 2  # Catalog + first completion; retry was denied before network.
    with db.session() as session:
        rows = session.scalars(select(AIRequest).order_by(AIRequest.id)).all()
        assert [row.status for row in rows] == ["success", "rate_limited"]
        assert rows[0].charged_tokens == 0 and rows[1].charged_tokens > 0


@pytest.fixture
def context_for_budget():
    from papertrade.ai.schema import MarketContext
    return MarketContext(symbol="BTC/USD", asset_class="crypto", data_timestamp=NOW.replace(second=0),
        current_price=100.0, recent_candles=[dict(timestamp=NOW.replace(second=0)-timedelta(minutes=15),
        open=99.0, high=101.0, low=98.0, close=100.0, volume=50.0)],
        trend_indicators={"trend_strength": 1.0}, momentum_indicators={"rsi14": 60.0},
        volatility={"volatility": .001}, volume={"last": 50.0},
        support_resistance={"support": 98.0, "resistance": 101.0},
        quant_prediction=dict(probability=.7, expected_return=.01, regime="uptrend", model_version="fixture-v1"),
        positions=[])
