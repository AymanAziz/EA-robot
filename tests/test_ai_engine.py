"""AI fusion behavior through the persistent engine and local simulator.

Prices, quant inference and cached AI here are explicit test fixtures. No external
provider or broker is contacted and these results are not trading-performance data.
"""
from datetime import timedelta
from types import SimpleNamespace

import httpx
import pandas as pd
from sqlalchemy import select

from papertrade.ai.fusion import seal_certificate, strategy_policy
from papertrade.brokers.simulator import LocalPaperSimulator
from papertrade.domain import OrderRequest, Quote, utcnow
from papertrade.engine import TradingEngine
from papertrade.models import InstrumentRow, SignalRow, StrategyObservation


class FixtureSource:
    def __init__(self, now):
        self.now = now
        self.candles = pd.DataFrame(
            {"open": 50000., "high": 50100., "low": 49900., "close": 50000., "volume": 1000.},
            index=pd.date_range(end=pd.Timestamp(now).floor("15min") - pd.Timedelta(minutes=15),
                                periods=130, freq="15min"))

    def get_market_data(self, symbol, start, end):
        return self.candles.loc[(self.candles.index >= start) & (self.candles.index < end)].copy()

    def get_quote(self, symbol):
        return Quote(49990., 50000., self.now - timedelta(seconds=1))


class CachedAIFixture:
    """A cache seam, deliberately without any provider/network capability."""
    def __init__(self, settings, now, available=True):
        self.calls = 0
        close = now.replace(second=0, microsecond=0)
        response = dict(symbol="BTC/USD", recommendation="BUY", direction_bias="long", market_regime="bullish",
            risk_level="low", confidence=.75, data_timestamp=close.isoformat(),
            reasoning_summary="Trend and momentum agree", supporting_factors=["Positive momentum"],
            risk_factors=["Execution costs remain uncertain"])
        self.row = SimpleNamespace(id=None, response=response, provider="groq", model="configured-model",
                                   created_at=now - timedelta(seconds=5), data_timestamp=close) if available else None
        self.cert = seal_certificate(dict(schema_version=1, strategy=settings.strategy, symbol="BTC/USD",
            quant_model_version="quant-test-fixture", ai_provider="groq", ai_model="configured-model",
            policy_sha256=strategy_policy(settings)["sha256"], accepted=True, approved=True,
            criteria={"test_fixture_only": True}, source="forward_replay", report_sha256="test-fixture-report",
            created_at=(now - timedelta(minutes=1)).isoformat(), approved_at=(now - timedelta(seconds=30)).isoformat(),
            expires_at=(now + timedelta(days=1)).isoformat()))

    def cached(self, symbol, now=None):
        self.calls += 1
        return self.row

    def certificate(self, symbol, model_version):
        return self.cert

    def analyze(self, *args, **kwargs):
        raise AssertionError("The order execution path must never call an AI provider")


def configured_engine(settings, db, *, strategy="ai_filtered_quant", ai_available=True,
                      probability=.8, expected_return=.05):
    now = pd.Timestamp(utcnow()).floor("15min").to_pydatetime() + timedelta(seconds=20)
    settings = settings.model_copy(update={"strategy": strategy, "strategy_execution_enabled": True,
                                          "ai_enabled": True, "groq_model": "configured-model"})
    with db.session() as session:
        for row in session.scalars(select(InstrumentRow)):
            row.enabled = row.symbol == "BTC/USD"
    source = FixtureSource(now)
    broker = LocalPaperSimulator(settings.state_dir / "simulator.db", settings.capital,
                                 quote_provider=source.get_quote, data_provider=source.get_market_data,
                                 clock=lambda: now)
    cache = CachedAIFixture(settings, now, available=ai_available)
    def predictor(*args, **kwargs):
        return SimpleNamespace(probability=probability, expected_return=expected_return, regime="trend",
                               model_version="quant-test-fixture", threshold=.65, atr=100.)
    engine = TradingEngine(settings, db, {"simulator": broker}, {"crypto": source}, predictor,
                           clock=lambda: now, ai_service=cache)
    assert engine.monitor_once(now)
    return engine, broker, cache, now


def test_ai_outage_holds_dependent_strategy_and_preserves_quant_only_independence(settings, db):
    engine, broker, cache, now = configured_engine(settings, db, ai_available=False)
    assert engine.run_once(now)["status"] == "success"
    assert broker.get_fills() == []
    with db.session() as session:
        assert session.scalar(select(SignalRow)).action == "HOLD"
        assert session.scalar(select(StrategyObservation)).fused_action == "HOLD"
    # A later quarter with explicitly enabled quant-only can operate without AI.
    other_db_path = settings.state_dir / "independent.db"
    from papertrade.db import Database
    independent_settings = settings.model_copy(update={"database_url": f"sqlite:///{other_db_path}"})
    other = Database(independent_settings)
    other.initialize()
    quant, quant_broker, _, quarter = configured_engine(independent_settings, other,
                                                       strategy="quant_only", ai_available=False)
    assert quant.run_once(quarter)["status"] == "success"
    assert len(quant_broker.get_fills()) == 1
    other.engine.dispose()


def test_independent_risk_denial_remains_final_even_with_ai_and_certificate(settings, db):
    engine, broker, cache, now = configured_engine(settings, db)
    db.set_control("paused", True)
    assert engine.run_once(now)["status"] == "success"
    assert broker.get_fills() == []
    with db.session() as session:
        signal = session.scalar(select(SignalRow))
        assert signal.action == "HOLD" and signal.reason == "paused"


def test_ai_never_creates_buy_when_quantitative_model_has_no_edge(settings, db):
    engine, broker, cache, now = configured_engine(settings, db, probability=.3)
    assert engine.run_once(now)["status"] == "success"
    assert broker.get_fills() == []
    with db.session() as session:
        signal = session.scalar(select(SignalRow))
        assert signal.action == "HOLD" and signal.reason == "probability_below_threshold"


def test_order_execution_reads_ai_cache_without_provider_http_or_duplicate_orders(settings, db, monkeypatch):
    def network_forbidden(*args, **kwargs):
        raise AssertionError("Unexpected network request in cache-only execution")
    monkeypatch.setattr(httpx.Client, "request", network_forbidden)
    engine, broker, cache, now = configured_engine(settings, db)
    assert engine.run_once(now)["status"] == "success"
    assert cache.calls >= 1 and len(broker.get_fills()) == 1
    assert engine.run_once(now)["reason"] == "slot_already_processed"
    assert len(broker.get_fills()) == 1


def test_quantitative_reducing_exit_survives_missing_ai_validation_and_execution_opt_in(settings, db):
    engine, broker, cache, now = configured_engine(settings, db, ai_available=False, probability=.2,
                                                 expected_return=-.02)
    engine.settings = engine.settings.model_copy(update={"strategy_execution_enabled": False})
    broker.submit_order(OrderRequest("BTC/USD", "buy", .01, "explicit-test-entry", 50000., 48000., 53000.))
    assert engine.run_once(now)["status"] == "success"
    assert broker.get_positions() == []
    fills = broker.get_fills()
    assert len(fills) == 2 and fills[-1].side == "sell"
    with db.session() as session:
        signal = session.scalar(select(SignalRow))
        assert signal.action == "CLOSE"


def test_quant_reducing_exit_is_not_blocked_by_a_broken_ai_cache(settings, db):
    engine, broker, cache, now = configured_engine(settings, db, probability=.2, expected_return=-.02)
    def unavailable(*args, **kwargs):
        raise ValueError("Corrupt or unavailable AI cache fixture")
    cache.cached = unavailable
    cache.certificate = unavailable
    broker.submit_order(OrderRequest("BTC/USD", "buy", .01, "explicit-cache-failure-entry",
                                     50000., 48000., 53000.))
    assert engine.run_once(now)["status"] == "success"
    assert broker.get_positions() == []
    assert len(broker.get_fills()) == 2
    with db.session() as session:
        assert session.scalar(select(SignalRow)).action == "CLOSE"


def test_explicit_quant_only_entry_is_independent_of_broken_ai_cache(settings, db):
    engine, broker, cache, now = configured_engine(settings, db, strategy="quant_only")
    def unavailable(*args, **kwargs):
        raise ValueError("Corrupt or unavailable AI cache fixture")
    cache.cached = unavailable
    cache.certificate = unavailable
    assert engine.run_once(now)["status"] == "success"
    assert len(broker.get_fills()) == 1
