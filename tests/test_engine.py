"""Engine behavior through its run/reconcile/control interfaces.

Synthetic candles and predictions are deliberately test fixtures; the production
engine only accepts its trained-model loader and real configured market sources.
"""
from datetime import timedelta
from types import SimpleNamespace

import httpx
import pandas as pd
from pydantic import SecretStr
from sqlalchemy import select

from papertrade.brokers.alpaca import AlpacaPaper
from papertrade.brokers.simulator import LocalPaperSimulator
from papertrade.domain import Account, BrokerOrder, OrderRequest, Position, Quote, utcnow
from papertrade.engine import TradingEngine
from papertrade.models import Health, InstrumentRow, OrderRow, Run, SignalRow


class FixtureSource:
    def __init__(self, now):
        self.now = now
        index = pd.date_range(end=pd.Timestamp(now).floor("15min") - pd.Timedelta(minutes=15),
                              periods=130, freq="15min")
        self.candles = pd.DataFrame({"open": 50000.0, "high": 50100.0, "low": 49900.0,
                                    "close": 50000.0, "volume": 1000.0}, index=index)

    def get_market_data(self, symbol, start, end):
        return self.candles.loc[(self.candles.index >= start) & (self.candles.index < end)].copy()

    def get_quote(self, symbol):
        return Quote(49990, 50000, self.now - timedelta(seconds=1))


def supported_prediction(candles, instrument, settings, now=None):
    return SimpleNamespace(probability=0.80, expected_return=0.05, regime="trend",
                           model_version="test-fixture-not-a-real-model", threshold=0.65, atr=100)


def analysis_time():
    return pd.Timestamp(utcnow()).floor("15min").to_pydatetime() + timedelta(seconds=20)


def only_btc(db):
    with db.session() as session:
        for row in session.scalars(select(InstrumentRow)):
            row.enabled = row.symbol == "BTC/USD"


def local_engine(settings, db, now):
    source = FixtureSource(now)
    broker = LocalPaperSimulator(settings.state_dir / "simulator.db", settings.capital,
                                 quote_provider=source.get_quote, data_provider=source.get_market_data,
                                 clock=lambda: now)
    engine = TradingEngine(settings, db, {"simulator": broker}, {"crypto": source}, supported_prediction,
                           clock=lambda: now)
    assert engine.monitor_once(now)
    return engine, broker


def test_analysis_executes_persistent_local_paper_fill_once_per_candle(settings, db):
    now = analysis_time()
    only_btc(db)
    engine, broker = local_engine(settings, db, now)
    result = engine.run_once(now)
    assert result["status"] == "success"
    assert len(broker.get_positions()) == 1
    assert len(broker.get_fills()) == 1
    restarted, _ = local_engine(settings, db, now)
    assert restarted.run_once(now)["reason"] == "slot_already_processed"
    assert len(broker.get_fills()) == 1
    with db.session() as session:
        orders = session.scalars(select(OrderRow)).all()
        assert len(orders) == 1 and orders[0].status == "filled"


def test_kill_switch_flattens_local_positions_and_blocks_new_entries(settings, db):
    now = analysis_time()
    only_btc(db)
    engine, broker = local_engine(settings, db, now)
    broker.submit_order(OrderRequest("BTC/USD", "buy", 0.01, "manual-paper-entry", 50000, 49000, 52000))
    result = engine.control("kill", actor="test-admin")
    assert result["killed"] and result["paused"]
    assert broker.get_positions() == []
    assert len(broker.get_fills()) == 2
    engine.run_once(now)
    assert broker.get_positions() == []
    assert len(broker.get_fills()) == 2


def test_missing_model_disables_symbol_and_records_hold(settings, db):
    now = analysis_time()
    only_btc(db)
    engine, broker = local_engine(settings, db, now)
    def unavailable(*args, **kwargs):
        raise ValueError("No valid trained model")
    engine.predictor = unavailable
    engine.run_once(now)
    assert broker.get_fills() == []
    with db.session() as session:
        signal = session.scalar(select(SignalRow))
        assert signal.action == "HOLD" and signal.reason == "model_unavailable_or_invalid"
        assert session.get(Health, "model:BTC/USD").status == "disabled"


def test_software_protection_requires_independent_monitor_before_new_entry(settings, db):
    now = analysis_time()
    only_btc(db)
    source = FixtureSource(now)
    broker = LocalPaperSimulator(settings.state_dir / "simulator.db", settings.capital,
                                 quote_provider=source.get_quote, clock=lambda: now)
    engine = TradingEngine(settings, db, {"simulator": broker}, {"crypto": source}, supported_prediction,
                           clock=lambda: now)
    engine.run_once(now)
    assert broker.get_fills() == []
    with db.session() as session:
        signal = session.scalar(select(SignalRow))
        assert signal.action == "HOLD" and signal.reason == "protection_unavailable"


def hosted_engine(settings, db, now, *, uncertain=False, outage=False):
    source = FixtureSource(now)
    state = {"posts": 0, "order": None, "visible": not uncertain}
    def respond(request):
        path = request.url.path
        if path == "/v2/account":
            if outage:
                return httpx.Response(503, json={"private": "must not escape"})
            return httpx.Response(200, json={"status": "ACTIVE", "currency": "USD", "equity": "10000",
                                           "cash": "10000", "trading_blocked": False, "account_blocked": False})
        if path == "/v2/positions":
            return httpx.Response(200, json=[])
        if path == "/v2/orders:by_client_order_id":
            return httpx.Response(200, json=state["order"]) if state["order"] and state["visible"] else httpx.Response(404)
        if path.startswith("/v2/orders/"):
            return httpx.Response(200, json=state["order"])
        if path == "/v2/account/activities/FILL":
            return httpx.Response(200, json=[])
        if "/assets/" in path:
            return httpx.Response(200, json={"status": "active", "tradable": True})
        if path.endswith("/latest/quotes"):
            return httpx.Response(200, json={"quotes": {"BTC/USD": {"bp": 49990, "ap": 50000,
                                                                   "t": (now - timedelta(seconds=1)).isoformat()}}})
        if path == "/v2/orders" and request.method == "GET":
            return httpx.Response(200, json=[state["order"]] if state["order"] and state["visible"] else [])
        if path == "/v2/orders" and request.method == "POST":
            import json
            payload = json.loads(request.content)
            state["posts"] += 1
            state["order"] = {"id": "paper-order-1", "client_order_id": payload["client_order_id"],
                              "symbol": "BTC/USD", "side": "buy", "qty": payload["qty"],
                              "status": "accepted", "filled_qty": "0", "filled_avg_price": None}
            if uncertain:
                raise httpx.ReadTimeout("sensitive transport internals", request=request)
            return httpx.Response(200, json=state["order"])
        raise AssertionError(f"Unexpected mocked request {request.method} {path}")
    settings = settings.model_copy(update={"execution": "brokers", "allow_unhosted_protection": True,
                                           "watchdog_url": SecretStr("")})
    db.health("watchdog", "ok", "Test fixture independent monitor", now)
    db.health("external_watchdog", "ok", "Test fixture external observer", now)
    broker = AlpacaPaper("fixture-paper-key", "fixture-secret", transport=httpx.MockTransport(respond))
    engine = TradingEngine(settings, db, {"alpaca": broker}, {"crypto": source}, supported_prediction,
                           clock=lambda: now)
    return engine, broker, state


def test_broker_acceptance_reserves_capacity_without_inventing_fill(settings, db):
    now = analysis_time()
    only_btc(db)
    engine, broker, state = hosted_engine(settings, db, now)
    engine.run_once(now)
    assert state["posts"] == 1
    assert broker.get_positions() == [] and broker.get_fills() == []
    assert engine.portfolio.reserved_positions == 1 and engine.portfolio.reserved_exposure > 0
    with db.session() as session:
        order = session.scalar(select(OrderRow))
        assert order.status == "accepted" and order.filled_qty == 0 and order.filled_avg_price is None


def test_uncertain_submission_is_found_after_restart_without_resubmission(settings, db):
    now = analysis_time()
    only_btc(db)
    engine, broker, state = hosted_engine(settings, db, now, uncertain=True)
    assert engine.run_once(now)["status"] == "degraded"
    assert state["posts"] == 1
    with db.session() as session:
        assert session.scalar(select(OrderRow)).status == "uncertain"
    state["visible"] = True
    restarted = TradingEngine(engine.settings, db, {"alpaca": broker}, engine.sources, supported_prediction,
                              clock=lambda: now)
    assert restarted.reconcile(now)
    assert restarted.run_once(now)["reason"] == "slot_already_processed"
    assert state["posts"] == 1
    with db.session() as session:
        assert session.scalar(select(OrderRow)).status == "accepted"


def test_broker_outage_blocks_every_new_entry(settings, db):
    now = analysis_time()
    only_btc(db)
    engine, broker, state = hosted_engine(settings, db, now, outage=True)
    assert engine.run_once(now)["status"] == "degraded"
    assert state["posts"] == 0
    assert not engine.portfolio.reconciled
    with db.session() as session:
        assert session.get(Health, "broker:alpaca").status == "error"


def test_repeated_reconciliation_of_protective_order_without_client_id_is_idempotent(settings, db):
    from papertrade.domain import Account, BrokerOrder
    class ProtectiveBroker:
        name = "oanda"
        def get_account(self):
            return Account("oanda", 10000, 10000)
        def get_positions(self):
            return []
        def get_open_orders(self):
            return [BrokerOrder("protective-10", "", "EUR/USD", "sell", 100, "accepted")]
        def get_fills(self, since=None):
            return []
        def get_order_status(self, order_id):
            return self.get_open_orders()[0]
    engine = TradingEngine(settings, db, {"oanda": ProtectiveBroker()}, {"crypto": FixtureSource(utcnow())}, supported_prediction)
    assert engine.reconcile()
    assert engine.reconcile()
    with db.session() as session:
        assert len(session.scalars(select(OrderRow)).all()) == 1


def test_restart_marks_interrupted_run_and_still_preserves_candle_dedup(settings, db):
    now = analysis_time()
    only_btc(db)
    with db.session() as session:
        session.add(Run(slot=(now - timedelta(minutes=30)).isoformat(), status="running"))
    engine, broker = local_engine(settings, db, now)
    engine.run_once(now)
    with db.session() as session:
        statuses = [r.status for r in session.scalars(select(Run).order_by(Run.id))]
    assert statuses == ["interrupted", "success"]
    assert len(broker.get_fills()) == 1


def test_reconciliation_includes_position_that_fills_during_status_lookup(settings, db):
    from papertrade.domain import Account, BrokerOrder, Position
    class FillsDuringLookup:
        name = "alpaca"
        filled = False
        def get_account(self):
            return Account("alpaca", 10000, 9500 if self.filled else 10000)
        def get_positions(self):
            return [Position("SPY", 1, 500, 500, "alpaca")] if self.filled else []
        def get_open_orders(self):
            return []
        def get_fills(self, since=None):
            return []
        def get_order_status(self, order_id):
            self.filled = True
            return BrokerOrder("fill-race", "race-entry", "SPY", "buy", 1, "filled", 1, 500)
    with db.session() as session:
        session.add(OrderRow(client_order_id="race-entry", broker="alpaca", broker_order_id="fill-race",
                             symbol="SPY", action="BUY", side="buy", qty=1, reference_price=500, status="accepted"))
    engine = TradingEngine(settings, db, {"alpaca": FillsDuringLookup()},
                           {"crypto": FixtureSource(utcnow())}, supported_prediction)
    assert engine.reconcile()
    assert len(engine.positions) == 1
    assert engine.accounts["alpaca"].cash == 9500


def test_external_buy_with_unknown_price_blocks_further_risk(settings, db):
    from papertrade.domain import Account, BrokerOrder
    now = analysis_time()
    only_btc(db)
    class ExternalUnknownBuy:
        name = "alpaca"
        posts = 0
        order = BrokerOrder("manual-open", "manual-client", "TSLA", "buy", 100, "accepted")
        def get_account(self):
            return Account("alpaca", 10000, 10000)
        def get_positions(self):
            return []
        def get_open_orders(self):
            return [self.order]
        def get_fills(self, since=None):
            return []
        def get_order_status(self, order_id):
            return self.order
        def is_market_open(self, symbol, now):
            return True
        def get_quote(self, symbol):
            return Quote(49990, 50000, now - timedelta(seconds=1))
        def supports_protection(self, symbol):
            return True
        def submit_order(self, request):
            self.posts += 1
            return BrokerOrder("new-entry", request.client_order_id, request.symbol, "buy", request.qty, "accepted")
    broker = ExternalUnknownBuy()
    settings = settings.model_copy(update={"execution": "brokers", "watchdog_url": SecretStr("https://example.com/test")})
    engine = TradingEngine(settings, db, {"alpaca": broker}, {"crypto": FixtureSource(now)}, supported_prediction,
                           clock=lambda: now)
    engine.run_once(now)
    assert broker.posts == 0


class MockPaperAccount:
    """External broker lifecycle fixture, including genuinely asynchronous leg cancellation state."""
    name = "alpaca"

    def __init__(self, now, *, symbol="BTC/USD", hosted=False, with_legs=False, quote_at=None):
        self.symbol = symbol
        self.qty = 1 if symbol == "SPY" else 0.01
        self.price = 500 if symbol == "SPY" else 47000
        self.hosted = hosted
        self.quote_at = quote_at or now - timedelta(seconds=1)
        self.posts = 0
        self.orders = {}
        if with_legs:
            for leg in ("stop", "target"):
                self.orders[leg] = BrokerOrder(leg, "", symbol, "sell", self.qty, "new",
                    order_type="stop" if leg == "stop" else "limit",
                    stop_price=self.price - 10 if leg == "stop" else None,
                    limit_price=self.price + 20 if leg == "target" else None)

    def get_account(self):
        return Account(self.name, 10000, 9500 if self.qty else 10000)

    def get_positions(self):
        return [Position(self.symbol, self.qty, self.price, self.price, self.name)] if self.qty else []

    def get_open_orders(self):
        return [o for o in self.orders.values() if o.status not in {"filled", "canceled", "rejected", "expired"}]

    def get_order_status(self, order_id):
        return self.orders[order_id]

    def find_order(self, client_order_id):
        return next((o for o in self.orders.values() if o.client_order_id == client_order_id), None)

    def get_fills(self, since=None):
        return []

    def get_quote(self, symbol):
        return Quote(self.price, self.price + 1, self.quote_at)

    def supports_protection(self, symbol):
        return self.hosted

    def is_market_open(self, symbol, now):
        return True

    def cancel_order(self, order_id):
        o = self.orders[order_id]
        self.orders[order_id] = BrokerOrder(o.id, o.client_order_id, o.symbol, o.side, o.qty, "canceled",
            filled_qty=o.filled_qty, filled_avg_price=o.filled_avg_price, order_type=o.order_type,
            stop_price=o.stop_price, limit_price=o.limit_price)

    def submit_order(self, request):
        self.posts += 1
        assert request.side == "sell"
        assert request.qty <= self.qty
        self.qty -= request.qty
        result = BrokerOrder("close-1", request.client_order_id, request.symbol, request.side, request.qty,
                             "filled", request.qty, self.price)
        self.orders[result.id] = result
        return result


def record_crypto_entry(db, now, *, expires_at=None):
    with db.session() as session:
        session.add(OrderRow(client_order_id="known-crypto-entry", broker="alpaca", broker_order_id="known-entry-1",
                             symbol="BTC/USD", action="BUY", side="buy", qty=0.01, reference_price=50000,
                             status="filled", filled_qty=0.01, filled_avg_price=50000, stop_loss=49000,
                             take_profit=52000, created_at=now - timedelta(minutes=10), expires_at=expires_at))


def test_kill_closes_position_with_recorded_protective_legs_in_same_cycle(settings, db):
    now = analysis_time()
    broker = MockPaperAccount(now, symbol="SPY", hosted=True, with_legs=True)
    settings = settings.model_copy(update={"execution": "brokers"})
    engine = TradingEngine(settings, db, {"alpaca": broker}, {}, supported_prediction, clock=lambda: now)
    assert engine.reconcile(now)
    engine.control("kill", actor="test-admin")
    assert broker.posts == 1
    assert broker.get_positions() == []
    with db.session() as session:
        assert session.get(Health, "monitor").status == "ok"


def test_fresh_quote_after_monitor_start_still_triggers_software_stop(settings, db):
    start = analysis_time()
    broker = MockPaperAccount(start, quote_at=start + timedelta(seconds=2))
    settings = settings.model_copy(update={"execution": "brokers", "allow_unhosted_protection": True})
    record_crypto_entry(db, start)
    engine = TradingEngine(settings, db, {"alpaca": broker}, {}, supported_prediction,
                           clock=lambda: start + timedelta(seconds=3))
    assert engine.monitor_once(start)
    assert broker.posts == 1
    assert broker.get_positions() == []


def test_disabling_unhosted_entries_does_not_abandon_existing_software_stop(settings, db):
    now = analysis_time()
    broker = MockPaperAccount(now)
    settings = settings.model_copy(update={"execution": "brokers", "allow_unhosted_protection": False})
    record_crypto_entry(db, now)
    engine = TradingEngine(settings, db, {"alpaca": broker}, {}, supported_prediction, clock=lambda: now)
    assert engine.monitor_once(now)
    assert broker.posts == 1
    assert broker.get_positions() == []


def test_holding_expiry_closes_without_loading_a_model(settings, db):
    now = analysis_time()
    broker = MockPaperAccount(now, hosted=True)
    settings = settings.model_copy(update={"execution": "brokers"})
    record_crypto_entry(db, now, expires_at=now - timedelta(seconds=1))
    def missing_model(*args, **kwargs):
        raise AssertionError("Protection monitoring must not require model inference")
    engine = TradingEngine(settings, db, {"alpaca": broker}, {}, missing_model, clock=lambda: now)
    assert engine.monitor_once(now)
    assert broker.posts == 1
    assert broker.get_positions() == []


def test_partial_bracket_entry_with_inactive_protection_is_canceled_and_flattened(settings, db):
    now = analysis_time()
    broker = MockPaperAccount(now, symbol="SPY", hosted=True, with_legs=True)
    broker.orders["partial-entry"] = BrokerOrder("partial-entry", "partial-client", "SPY", "buy", 2,
                                                  "partially_filled", 1, 500, order_type="market")
    broker.orders["stop"] = BrokerOrder("stop", "", "SPY", "sell", 2, "held", order_type="stop", stop_price=490)
    broker.orders["target"] = BrokerOrder("target", "", "SPY", "sell", 2, "held", order_type="limit", limit_price=520)
    settings = settings.model_copy(update={"execution": "brokers"})
    engine = TradingEngine(settings, db, {"alpaca": broker}, {}, supported_prediction, clock=lambda: now)
    assert engine.monitor_once(now)
    assert broker.orders["partial-entry"].status == "canceled"
    assert broker.posts == 1 and broker.get_positions() == []


def test_manually_canceled_hosted_stop_causes_prompt_exit_of_unprotected_position(settings, db):
    now = analysis_time()
    broker = MockPaperAccount(now, symbol="SPY", hosted=True, with_legs=True)
    settings = settings.model_copy(update={"execution": "brokers"})
    engine = TradingEngine(settings, db, {"alpaca": broker}, {}, supported_prediction, clock=lambda: now)
    assert engine.reconcile(now)
    broker.cancel_order("stop")
    assert engine.monitor_once(now)
    assert broker.posts == 1 and broker.get_positions() == []


def test_confirmed_hosted_stop_and_target_covering_position_are_preserved(settings, db):
    now = analysis_time()
    broker = MockPaperAccount(now, symbol="SPY", hosted=True, with_legs=True)
    settings = settings.model_copy(update={"execution": "brokers"})
    engine = TradingEngine(settings, db, {"alpaca": broker}, {}, supported_prediction, clock=lambda: now)
    assert engine.monitor_once(now)
    assert broker.posts == 0 and len(broker.get_positions()) == 1
