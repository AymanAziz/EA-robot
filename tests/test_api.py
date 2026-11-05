import base64
import json
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from papertrade.api import create_app
from papertrade.domain import utcnow
from papertrade.engine import TradingEngine
from papertrade.logging import redact
from papertrade.models import Run
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
