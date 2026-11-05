from datetime import datetime, timedelta, timezone

import httpx
import pytest

from papertrade.brokers.alpaca import AlpacaPaper
from papertrade.brokers.oanda import OandaPractice
from papertrade.brokers.simulator import LocalPaperSimulator
from papertrade.domain import BrokerError, OrderRejected, OrderRequest, Quote, SubmissionUnknown


def test_alpaca_rejects_redirect_to_live_endpoint():
    seen = []
    def respond(request):
        seen.append(str(request.url))
        return httpx.Response(302, headers={"location": "https://api.alpaca.markets/v2/account"})
    broker = AlpacaPaper("paper-key", "paper-secret", transport=httpx.MockTransport(respond))
    with pytest.raises(BrokerError):
        broker.get_account()
    assert seen == ["https://paper-api.alpaca.markets/v2/account"]


def alpaca_handler(post_response):
    def respond(request):
        assert request.url.host in {"paper-api.alpaca.markets", "data.alpaca.markets"}
        if request.method == "POST":
            return post_response(request)
        path = request.url.path
        if path.endswith("orders:by_client_order_id"):
            return httpx.Response(404)
        if path.endswith("/account"):
            return httpx.Response(200, json={"equity": "10000", "cash": "10000", "currency": "USD",
                                           "status": "ACTIVE", "trading_blocked": False, "account_blocked": False})
        if "/assets/" in path:
            return httpx.Response(200, json={"tradable": True, "status": "active"})
        if path.endswith("/positions"):
            return httpx.Response(200, json=[])
        if path.endswith("/clock"):
            return httpx.Response(200, json={"is_open": True})
        raise AssertionError(path)
    return respond


def stock_request(key="entry-1"):
    return OrderRequest("SPY", "buy", 1, key, 500, 490, 520)


def test_alpaca_submission_timeout_is_uncertain_and_not_retried():
    attempts = []
    def timeout(request):
        attempts.append(request)
        raise httpx.ReadTimeout("secret response must never escape", request=request)
    broker = AlpacaPaper("key", "secret", transport=httpx.MockTransport(alpaca_handler(timeout)))
    with pytest.raises(SubmissionUnknown, match="reconcile") as error:
        broker.submit_order(stock_request())
    assert len(attempts) == 1
    assert "secret response" not in str(error.value)


def test_accepted_alpaca_order_is_not_treated_as_filled():
    def accepted(request):
        import json
        payload = json.loads(request.content)
        assert payload["order_class"] == "bracket"
        return httpx.Response(200, json={"id": "broker-1", "client_order_id": payload["client_order_id"],
                                       "symbol": "SPY", "side": "buy", "qty": "1", "status": "accepted",
                                       "filled_qty": "0", "filled_avg_price": None})
    broker = AlpacaPaper("key", "secret", transport=httpx.MockTransport(alpaca_handler(accepted)))
    result = broker.submit_order(stock_request())
    assert result.status == "accepted" and result.filled_qty == 0 and result.filled_avg_price is None


def test_broker_rejection_is_distinguished_from_transport_uncertainty():
    broker = AlpacaPaper("key", "secret", transport=httpx.MockTransport(
        alpaca_handler(lambda request: httpx.Response(422, json={"message": "private"}))))
    with pytest.raises(OrderRejected, match="422"):
        broker.submit_order(stock_request())


def test_broker_crypto_protection_is_not_advertised():
    broker = AlpacaPaper("key", "secret", transport=httpx.MockTransport(lambda r: httpx.Response(500)))
    assert broker.supports_protection("SPY")
    assert not broker.supports_protection("BTC/USD")


def test_alpaca_open_orders_include_nested_protective_legs():
    data = [{"id": "parent", "client_order_id": "open", "symbol": "SPY", "side": "buy", "qty": "1",
             "status": "filled", "filled_qty": "1", "filled_avg_price": "500", "legs": [
                 {"id": "stop", "client_order_id": "stop", "symbol": "SPY", "side": "sell", "qty": "1",
                  "status": "new", "filled_qty": "0", "filled_avg_price": None}]}]
    broker = AlpacaPaper("key", "secret", transport=httpx.MockTransport(lambda r: httpx.Response(200, json=data)))
    orders = broker.get_open_orders()
    assert [(o.id, o.symbol, o.side) for o in orders] == [("stop", "SPY", "sell")]


def test_alpaca_preserves_actual_protection_order_types_prices_and_held_state():
    rows = [{"id": "stop", "client_order_id": "stop-leg", "symbol": "SPY", "side": "sell", "qty": "2",
             "status": "held", "filled_qty": "0", "type": "stop", "stop_price": "490.00"},
            {"id": "target", "client_order_id": "target-leg", "symbol": "SPY", "side": "sell", "qty": "2",
             "status": "new", "filled_qty": "0", "type": "limit", "limit_price": "520.00"}]
    broker = AlpacaPaper("key", "secret", transport=httpx.MockTransport(lambda r: httpx.Response(200, json=rows)))
    stop, target = broker.get_open_orders()
    assert (stop.order_type, stop.stop_price, stop.status, stop.qty) == ("stop", 490, "held", 2)
    assert (target.order_type, target.limit_price, target.status) == ("limit", 520, "new")


def test_simulator_requires_real_quotes(tmp_path):
    broker = LocalPaperSimulator(tmp_path / "ledger.db")
    with pytest.raises(BrokerError, match="No real quote"):
        broker.submit_order(OrderRequest("BTC/USD", "buy", 0.01, "entry", 50000, 49000, 52000))
    assert broker.get_account().equity == 10000


def test_simulator_fill_persists_and_duplicate_order_does_not_spend_again(tmp_path):
    path = tmp_path / "ledger.db"
    broker = LocalPaperSimulator(path)
    broker.set_quote("BTC/USD", Quote(49990, 50000, datetime.now(timezone.utc)))
    request = OrderRequest("BTC/USD", "buy", 0.01, "entry", 50000, 49000, 52000)
    first = broker.submit_order(request)
    second = LocalPaperSimulator(path).submit_order(request)
    assert first == second
    assert first.filled_avg_price == pytest.approx(50050)
    assert broker.get_account().cash == pytest.approx(9498.24875)
    assert len(broker.get_fills()) == 1
    assert broker.get_positions()[0].qty == 0.01


def test_simulator_never_averages_down_or_opens_short(tmp_path):
    broker = LocalPaperSimulator(tmp_path / "ledger.db")
    broker.set_quote("BTC/USD", Quote(49990, 50000, datetime.now(timezone.utc)))
    broker.submit_order(OrderRequest("BTC/USD", "buy", 0.01, "entry", 50000, 49000, 52000))
    with pytest.raises(OrderRejected, match="Adding"):
        broker.submit_order(OrderRequest("BTC/USD", "buy", 0.01, "entry-two", 50000, 49000, 52000))
    with pytest.raises(OrderRejected, match="Short"):
        broker.submit_order(OrderRequest("BTC/USD", "sell", 0.02, "sell-too-much", 49990))


def test_simulator_rejects_stale_market_prices(tmp_path):
    broker = LocalPaperSimulator(tmp_path / "ledger.db")
    broker.set_quote("BTC/USD", Quote(49990, 50000, datetime.now(timezone.utc) - timedelta(minutes=3)))
    with pytest.raises(OrderRejected, match="Fresh executable"):
        broker.submit_order(OrderRequest("BTC/USD", "buy", 0.01, "entry", 50000, 49000, 52000))


def test_simulator_stop_fills_at_observed_adverse_gap_not_stop_price(tmp_path):
    broker = LocalPaperSimulator(tmp_path / "ledger.db")
    broker.set_quote("BTC/USD", Quote(49990, 50000, datetime.now(timezone.utc)))
    broker.submit_order(OrderRequest("BTC/USD", "buy", 0.01, "entry", 50000, 49000, 52000))
    exits = broker.process_protection("BTC/USD", Quote(47000, 47010, datetime.now(timezone.utc)))
    assert exits[0].filled_avg_price == pytest.approx(46953)
    assert broker.get_positions() == []
    assert len(broker.get_fills()) == 2
    assert broker.get_fills()[-1].realized_pl < -30


def test_oanda_never_follows_live_redirect():
    seen = []
    def respond(request):
        seen.append(str(request.url))
        return httpx.Response(302, headers={"location": "https://api-fxtrade.oanda.com/v3/accounts"})
    broker = OandaPractice("practice-token", "101-001-1-001", transport=httpx.MockTransport(respond))
    with pytest.raises(BrokerError, match="redirect"):
        broker.get_account()
    assert seen == ["https://api-fxpractice.oanda.com/v3/accounts"]


def test_oanda_mt4_accounts_fail_closed():
    def respond(request):
        return httpx.Response(200, json={"accounts": [{"id": "101-001-1-001", "mt4AccountID": 42}]})
    broker = OandaPractice("practice-token", "101-001-1-001", transport=httpx.MockTransport(respond))
    with pytest.raises(BrokerError, match="MT4"):
        broker.get_account()


def test_oanda_protective_orders_are_associated_with_position_symbol():
    def respond(request):
        if request.url.path.endswith("/pendingOrders"):
            return httpx.Response(200, json={"orders": [{"id": "10", "tradeID": "5", "type": "STOP_LOSS",
                                                        "state": "PENDING"}]})
        return httpx.Response(200, json={"trades": [{"id": "5", "instrument": "EUR_USD", "currentUnits": "100"}]})
    broker = OandaPractice("practice-token", "101-001-1-001", transport=httpx.MockTransport(respond))
    orders = broker.get_open_orders()
    assert [(o.symbol, o.side, o.qty) for o in orders] == [("EUR/USD", "sell", 100)]


def test_oanda_normalizes_actual_dependent_stop_and_target_metadata():
    def respond(request):
        if request.url.path.endswith("/pendingOrders"):
            return httpx.Response(200, json={"orders": [
                {"id": "10", "tradeID": "5", "type": "STOP_LOSS", "price": "1.09000", "state": "PENDING"},
                {"id": "11", "tradeID": "5", "type": "TAKE_PROFIT", "price": "1.12000", "state": "PENDING"}]})
        return httpx.Response(200, json={"trades": [{"id": "5", "instrument": "EUR_USD", "currentUnits": "100"}]})
    broker = OandaPractice("practice-token", "101-001-1-001", transport=httpx.MockTransport(respond))
    stop, target = broker.get_open_orders()
    assert (stop.symbol, stop.order_type, stop.stop_price, stop.qty, stop.status) == ("EUR/USD", "stop", 1.09, 100, "accepted")
    assert (target.symbol, target.order_type, target.limit_price, target.qty) == ("EUR/USD", "limit", 1.12, 100)


def oanda_handler(post_response, *, has_position=False):
    def respond(request):
        assert request.url.host == "api-fxpractice.oanda.com"
        path = request.url.path
        if request.method == "POST":
            return post_response(request)
        if "/orders/@" in path:
            return httpx.Response(404)
        if path == "/v3/accounts":
            return httpx.Response(200, json={"accounts": [{"id": "101-001-1-001"}]})
        if path.endswith("/summary"):
            return httpx.Response(200, json={"account": {"NAV": "10000", "balance": "10000", "currency": "USD"}})
        if path.endswith("/instruments"):
            return httpx.Response(200, json={"instruments": [{"name": "EUR_USD", "displayPrecision": 5,
                                                               "minimumTradeSize": "1"}]})
        if path.endswith("/openPositions"):
            positions = [{"instrument": "EUR_USD", "long": {"units": "100", "averagePrice": "1.10000",
                                                              "unrealizedPL": "1"},
                          "short": {"units": "0"}}] if has_position else []
            return httpx.Response(200, json={"positions": positions})
        if path.endswith("/pricing"):
            return httpx.Response(200, json={"prices": [{"instrument": "EUR_USD", "bids": [{"price": "1.10000"}],
                                                        "asks": [{"price": "1.10010"}], "status": "tradeable",
                                                        "time": datetime.now(timezone.utc).isoformat()}]})
        raise AssertionError(path)
    return respond


def test_oanda_long_open_has_hosted_protection_and_confirms_actual_fill():
    def filled(request):
        import json
        payload = json.loads(request.content)["order"]
        assert payload["positionFill"] == "OPEN_ONLY"
        assert payload["stopLossOnFill"]["price"] == "1.09000"
        assert payload["takeProfitOnFill"]["price"] == "1.12000"
        return httpx.Response(201, json={"orderCreateTransaction": {"id": "10", "units": "100",
                                                                   "instrument": "EUR_USD",
                                                                   "clientExtensions": {"id": "forex-entry"}},
                                        "orderFillTransaction": {"id": "11", "orderID": "10", "units": "100",
                                                                 "price": "1.10012", "commission": "0.01"}})
    broker = OandaPractice("practice-token", "101-001-1-001", transport=httpx.MockTransport(oanda_handler(filled)))
    result = broker.submit_order(OrderRequest("EUR/USD", "buy", 100, "forex-entry", 1.10, 1.09, 1.12))
    assert result.status == "filled" and result.filled_qty == 100
    assert result.filled_avg_price == 1.10012
    assert result.fees == 0.01


def test_oanda_sell_is_reduce_only_and_cannot_open_short():
    def filled(request):
        import json
        payload = json.loads(request.content)["order"]
        assert payload["positionFill"] == "REDUCE_ONLY"
        assert payload["units"] == "-100"
        assert "stopLossOnFill" not in payload
        return httpx.Response(201, json={"orderCreateTransaction": {"id": "12", "units": "-100",
                                                                   "instrument": "EUR_USD",
                                                                   "clientExtensions": {"id": "forex-exit"}},
                                        "orderFillTransaction": {"id": "13", "orderID": "12", "units": "-100",
                                                                 "price": "1.10000"}})
    broker = OandaPractice("practice-token", "101-001-1-001", transport=httpx.MockTransport(
        oanda_handler(filled, has_position=True)))
    result = broker.submit_order(OrderRequest("EUR/USD", "sell", 100, "forex-exit", 1.10, action="CLOSE"))
    assert result.side == "sell" and result.filled_qty == 100


def test_oanda_submission_with_create_only_is_pending_not_filled():
    def accepted(request):
        return httpx.Response(201, json={"orderCreateTransaction": {"id": "10", "units": "100",
                                                                   "instrument": "EUR_USD",
                                                                   "clientExtensions": {"id": "forex-entry"}}})
    broker = OandaPractice("practice-token", "101-001-1-001", transport=httpx.MockTransport(oanda_handler(accepted)))
    result = broker.submit_order(OrderRequest("EUR/USD", "buy", 100, "forex-entry", 1.10, 1.09, 1.12))
    assert result.status == "accepted" and result.filled_qty == 0 and result.filled_avg_price is None


def test_alpaca_missing_fee_is_provisional_not_confirmed_zero():
    row = {"id": "fill-1", "order_id": "order-1", "symbol": "BTCUSD", "side": "buy",
           "qty": "0.01", "price": "50000", "transaction_time": "2026-01-01T00:00:00Z"}
    broker = AlpacaPaper("key", "secret", transport=httpx.MockTransport(lambda r: httpx.Response(200, json=[row])))
    fill = broker.get_fills()[0]
    assert not fill.fees_final
    assert fill.symbol == "BTC/USD"


def test_alpaca_account_identity_is_stable_hash_not_raw_identifier():
    raw_id = "private-alpaca-paper-account-id"
    data = {"id": raw_id, "equity": "10000", "cash": "10000", "currency": "USD", "status": "ACTIVE",
            "trading_blocked": False, "account_blocked": False}
    broker = AlpacaPaper("key", "secret", transport=httpx.MockTransport(lambda r: httpx.Response(200, json=data)))
    account = broker.get_account()
    assert len(account.identity) == 64 and raw_id not in account.identity
    assert account.identity == broker.get_account().identity


def test_oanda_account_identity_is_hashed_without_exposing_account_number():
    broker = OandaPractice("practice-token", "101-001-1-001", transport=httpx.MockTransport(
        oanda_handler(lambda r: httpx.Response(500))))
    account = broker.get_account()
    assert len(account.identity) == 64 and "101-001-1-001" not in account.identity
    assert account.identity == broker.get_account().identity


def test_simulator_identity_survives_restart_but_changes_when_ledger_is_reset(tmp_path):
    path = tmp_path / "ledger.db"
    original = LocalPaperSimulator(path).get_account()
    restarted = LocalPaperSimulator(path, capital=50000).get_account()
    assert restarted.identity == original.identity
    assert restarted.cash == 10000
    path.unlink()
    reset = LocalPaperSimulator(path).get_account()
    assert reset.identity != original.identity


def test_simulator_migrates_old_ledger_identity_without_resetting_cash(tmp_path):
    import sqlite3
    path = tmp_path / "legacy.db"
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE account(id INTEGER PRIMARY KEY, cash REAL NOT NULL, capital REAL NOT NULL)")
        conn.execute("INSERT INTO account VALUES(1, 9734.56, 10000)")
    account = LocalPaperSimulator(path).get_account()
    assert account.cash == 9734.56
    assert len(account.identity) == 64
    assert account.identity == LocalPaperSimulator(path).get_account().identity
