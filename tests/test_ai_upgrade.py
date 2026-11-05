"""Upgrade acceptance through configuration, authenticated views and actual migration history."""
import json
from pathlib import Path

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError
import pytest
from sqlalchemy import select, text

from papertrade.api import create_app
from papertrade.config import Settings
from papertrade.db import Database
from papertrade.domain import utcnow
from papertrade.engine import TradingEngine
from papertrade.logging import redact
from papertrade.models import AIAnalysisRow, AIRequest


def test_environment_template_is_startable_and_execution_requires_explicit_opt_in():
    settings = Settings(_env_file=Path(__file__).resolve().parents[1] / ".env.example")
    assert settings.mode == "paper"
    assert settings.trading_interval_minutes == 15
    assert settings.ai_provider == "groq" and settings.ai_fallback_provider == "none"
    assert not settings.ai_enabled and not settings.ai_allow_paid and not settings.strategy_execution_enabled
    with pytest.raises(ValidationError):
        Settings(_env_file=None, ai_fallback_provider="hermes")
    with pytest.raises(ValidationError):
        Settings(_env_file=None, trading_interval_minutes=1)


def test_ai_credentials_are_redacted_and_not_returned_by_authenticated_views(settings, db):
    settings.groq_api_key = SecretStr("unit-test-groq-secret-value")
    settings.hermes_api_key = SecretStr("unit-test-hermes-secret-value")
    settings.api_token = SecretStr("unit-test-machine-key-at-least-thirty-two-chars")
    engine = TradingEngine(settings, db, brokers={}, sources={})
    api = TestClient(create_app(settings, db, engine))
    headers = {"Authorization": "Bearer " + settings.api_token.get_secret_value()}
    for table in ("ai_analyses", "ai_requests", "strategy_observations", "strategy_validations"):
        assert api.get(f"/tables/{table}").status_code == 401
        response = api.get(f"/tables/{table}", headers=headers)
        assert response.status_code == 200 and response.json() == {"rows": []}
    response = api.get("/status", headers=headers)
    assert response.status_code == 200
    payload = response.json()
    assert payload["ai"]["last_success"] is None
    assert payload["ai"]["usage"]["requests"] == 0
    assert payload["system_health"]["database"]["reachable"]
    assert "secret-value" not in response.text and "unit-test-machine-key" not in response.text
    assert redact("unit-test-groq-secret-value unit-test-hermes-secret-value", settings) == "[REDACTED] [REDACTED]"


def test_migration_preserves_existing_paper_history_and_adds_ai_tables(tmp_path, monkeypatch):
    path = tmp_path / "legacy.db"
    url = f"sqlite:///{path}"
    monkeypatch.setenv("PT_DATABASE_URL", url)
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    command.upgrade(config, "1a6d94dc11b7")
    database = Database(Settings(_env_file=None, database_url=url, state_dir=tmp_path))
    database.seed()
    with database.engine.begin() as connection:
        connection.execute(text("INSERT INTO controls(key,value) VALUES (:key,:value)"),
                           {"key": "preserved-audit-marker", "value": json.dumps({"history": "retain"})})
        connection.execute(text("INSERT INTO audit_logs(timestamp,actor,action,detail) VALUES (:time,:actor,:action,:detail)"),
            {"time": utcnow().isoformat(), "actor": "old-admin", "action": "old-paper-action", "detail": "{}"})
    command.upgrade(config, "head")
    assert database.control("preserved-audit-marker") == {"history": "retain"}
    with database.engine.connect() as connection:
        assert connection.execute(text("SELECT action FROM audit_logs WHERE actor='old-admin'")).scalar_one() == "old-paper-action"
    with database.session() as session:
        assert list(session.scalars(select(AIAnalysisRow))) == []
        assert list(session.scalars(select(AIRequest))) == []
    database.engine.dispose()


def test_model_discovery_explains_unverified_billing_without_sending_http(settings, db, monkeypatch, capsys):
    import httpx
    from papertrade.cli import main
    monkeypatch.setenv("PT_DATABASE_URL", settings.database_url)
    monkeypatch.setenv("PT_STATE_DIR", str(settings.state_dir))
    monkeypatch.setenv("PT_AI_ACCOUNT_TIER", "unverified")
    monkeypatch.setattr("sys.argv", ["papertrade", "ai-models", "--provider", "groq"])
    def forbidden(*args, **kwargs):
        raise AssertionError("Discovery must not send an HTTP request before account authorization")
    monkeypatch.setattr(httpx.Client, "request", forbidden)
    with pytest.raises(SystemExit):
        main()
    result = json.loads(capsys.readouterr().out)
    assert "confirmed free account" in result["error"]
