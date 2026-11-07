import base64
import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import event, insert

from papertrade.api import create_app
from papertrade.domain import utcnow
from papertrade.engine import TradingEngine
from papertrade.logging import redact
from papertrade.models import FillRow, PortfolioSnapshot, Run
from papertrade.security import issue_token, password_hasher, valid_token


@pytest.fixture
def client(settings, db):
    secured = settings.model_copy(update={"api_token": SecretStr("test-only-machine-key-with-at-least-32-characters"),
        "admin_password_hash": SecretStr(password_hasher.hash("test-only-long-password"))})
    engine = TradingEngine(secured, db, brokers={}, sources={})
    return TestClient(create_app(secured, db, engine)), secured


def login(client):
    response = client.post("/auth/login", json={"username": "admin", "password": "test-only-long-password"})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_every_administrative_action_requires_server_authentication(client, db):
    api, _ = client
    assert api.post("/controls", json={"action": "kill"}).status_code == 401
    assert not db.control("killed")
    assert api.get("/status").status_code == 401
    assert api.get("/tables/orders").status_code == 401
    assert api.post("/controls", json={"action": "kill"}, headers={"Authorization": "Bearer invalid"}).status_code == 401


def test_authenticated_controls_are_durable_and_auditable(client, db):
    api, settings = client
    headers = login(api)
    assert api.post("/controls", json={"action": "kill"}, headers=headers).json()["killed"]
    assert db.control("killed") and db.control("paused")
    status = api.get("/status", headers=headers)
    assert status.status_code == 200 and status.json()["mode"] == "paper"
    assert settings.api_token.get_secret_value() not in status.text
    assert api.post("/controls", json={"action": "resume"}, headers=headers).status_code == 200
    assert not db.control("killed")
    logs = api.get("/tables/audit_logs", headers=headers).json()["rows"]
    assert {"kill", "resume", "login"} <= {r["action"] for r in logs}
    assert all("password" not in json.dumps(r) for r in logs)


def test_status_metrics_remain_correct_without_materializing_minute_history(client, db):
    api, _ = client
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    snapshots = []
    for minute in range(10 * 24 * 60):
        day = minute // (24 * 60)
        equity = 10_000 if day == 0 else 11_000 if day == 1 else 9_000
        snapshots.append({"timestamp": start + timedelta(minutes=minute), "equity": equity,
            "cash": equity, "unrealized_pl": 0, "realized_pl": 0, "daily_pl": 0,
            "max_drawdown": 0.2 if day >= 2 else 0, "exposure": 0, "brokers": {}})
    fills = [{"broker": "simulator", "broker_fill_id": f"history-{i}",
              "broker_order_id": f"history-order-{i}", "symbol": "BTC/USD", "side": "buy",
              "qty": 1, "price": 100, "fee": 0, "fees_final": True, "realized_pl": None,
              "timestamp": start + timedelta(minutes=i)} for i in range(2_500)]
    fills.extend([
        {"broker": "simulator", "broker_fill_id": "closed-buy", "broker_order_id": "closed-order-buy",
         "symbol": "BTC/USD", "side": "buy", "qty": 1, "price": 100, "fee": 1,
         "fees_final": True, "realized_pl": None, "timestamp": start},
        {"broker": "simulator", "broker_fill_id": "closed-win", "broker_order_id": "closed-order-win",
         "symbol": "BTC/USD", "side": "sell", "qty": 1, "price": 110, "fee": 2,
         "fees_final": True, "realized_pl": 100, "timestamp": start + timedelta(days=1)},
        {"broker": "simulator", "broker_fill_id": "closed-loss", "broker_order_id": "closed-order-loss",
         "symbol": "BTC/USD", "side": "sell", "qty": 1, "price": 90, "fee": 3,
         "fees_final": True, "realized_pl": -50, "timestamp": start + timedelta(days=2)},
    ])
    with db.session() as session:
        session.execute(insert(PortfolioSnapshot), snapshots)
        session.execute(insert(FillRow), fills)

    materialized = {"snapshots": 0, "fills": 0}
    def snapshot_loaded(*_):
        materialized["snapshots"] += 1
    def fill_loaded(*_):
        materialized["fills"] += 1
    snapshot_queries = []
    def query_started(_connection, _cursor, statement, _parameters, _context, _executemany):
        normalized = statement.lower()
        if normalized.lstrip().startswith("select") and "portfolio_snapshots" in normalized:
            snapshot_queries.append(normalized)
    event.listen(PortfolioSnapshot, "load", snapshot_loaded)
    event.listen(FillRow, "load", fill_loaded)
    event.listen(db.engine, "before_cursor_execute", query_started)
    try:
        response = api.get("/status", headers=login(api))
    finally:
        event.remove(PortfolioSnapshot, "load", snapshot_loaded)
        event.remove(FillRow, "load", fill_loaded)
        event.remove(db.engine, "before_cursor_execute", query_started)

    assert response.status_code == 200
    status = response.json()
    assert status["equity"] == 9_000
    metrics = status["metrics"]
    assert metrics.pop("total_return") == pytest.approx(-0.1)
    assert metrics == {
        "win_rate": 0.5, "profit_factor": 2.0,
        "sharpe": None, "sortino": None, "max_drawdown": 0.2,
        "trade_count": 2, "fees_reported": 6.0, "fees_final": True,
        "by_market": {"crypto": 50.0}, "realized_pl_complete": True,
        "method": "Daily observed equity (20+ returns); FIFO net closed fill P/L; "
                  "missing basis unavailable; fees may be provisional",
    }
    assert materialized["snapshots"] <= 10
    assert materialized["fills"] <= 10
    assert len(snapshot_queries) <= 12
    assert sum("portfolio_snapshots.timestamp >=" in query and
               "portfolio_snapshots.timestamp <" in query for query in snapshot_queries) == 10
    assert all("group by" not in query and "date(" not in query for query in snapshot_queries)


def test_bad_login_is_rate_limited_without_exposing_credentials(client):
    api, _ = client
    for _ in range(5):
        assert api.post("/auth/login", json={"username": "admin", "password": "wrong"}).status_code == 401
    assert api.post("/auth/login", json={"username": "admin", "password": "wrong"}).status_code == 429


def test_sessions_expire_and_cannot_be_forged(client):
    _, settings = client
    assert valid_token(issue_token(settings), settings)
    assert not valid_token(issue_token(settings, lifetime=-10), settings)
    assert not valid_token(base64.urlsafe_b64encode(b"9999999999:nonce:forged").decode(), settings)
    assert not valid_token("!invalid-base64!", settings)


def test_dashboard_liveness_is_not_bot_readiness(client, db):
    api, _ = client
    assert api.get("/healthz").status_code == 200
    assert api.get("/readyz").status_code == 503
    # Successful scheduler alone is insufficient without market and broker facts.
    now = utcnow()
    db.health("scheduler", "ok", "done", now)
    with db.session() as session:
        session.add(Run(slot=now.isoformat(), status="success", finished_at=now))
    assert api.get("/readyz").status_code == 503
    db.health("broker:simulator", "ok", "connected", now)
    db.health("watchdog", "ok", "Independent monitoring succeeded", now)
    db.health("data:BTC/USD", "ok", "completed", now)
    from papertrade.domain import INSTRUMENTS
    for symbol in INSTRUMENTS:
        if symbol != "BTC/USD":
            db.health(f"data:{symbol}", "disabled", "Credentials missing", now)
    assert api.get("/readyz").status_code == 200
    db.health("broker:simulator", "ok", "old", now - timedelta(minutes=3))
    assert api.get("/readyz").status_code == 503


def test_missing_auth_configuration_remains_locked(settings, db):
    api = TestClient(create_app(settings, db, TradingEngine(settings, db, {}, {})))
    assert api.post("/auth/login", json={"username": "admin", "password": "anything"}).status_code == 401
    assert api.get("/status", headers={"Authorization": "Bearer "}).status_code == 401


def test_secret_redaction_covers_all_configured_values(settings):
    configured = settings.model_copy(update={"alpaca_key": SecretStr("test-secret-key"),
                                            "oanda_token": SecretStr("test-secret-token")})
    value = redact("test-secret-key test-secret-token Authorization: Bearer abc123 password=hello", configured)
    assert "test-secret" not in value and "abc123" not in value and "hello" not in value
