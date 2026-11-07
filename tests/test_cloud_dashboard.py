"""Cloud frontend behavior uses mocked HTTP; no Community Cloud publication is implied."""
from pathlib import Path
import json
import sys
import subprocess

import httpx
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from papertrade.dashboard import DashboardSettings, cloud_settings, comparison_metrics, validated_backend_url


ROOT = Path(__file__).resolve().parents[1]


def comparison_report():
    """Fixture-only metrics; never used as financial-market results."""
    metrics = {"total_return": -0.10, "max_drawdown": -0.20, "sharpe": -0.5,
               "profit_factor": 0.7, "trade_count": 5, "transaction_costs": 12.34}
    return {"source": "forward_replay", "observations_sha256": "fixture-observations",
        "policy_sha256": "fixture-policy", "quant_model_version": "fixture-quant",
        "ai_provider": "groq", "ai_model": "fixture-model",
        "split": {"validation": {"start": "2026-01-01", "end": "2026-01-02"},
                  "test": {"start": "2026-01-03", "end": "2026-01-04"}},
        "strategies": {**{name: {"accepted": False, "validation": {"metrics": metrics},
                                  "test": {"metrics": dict(metrics, trade_count=7)}}
                              for name in ("quant_only", "ai_filtered_quant", "hybrid")},
                       "ai_only_research": {"accepted": False, "metrics": None, "reason": "No execution"}},
        "benchmarks": {part: {name: {"metrics": dict(metrics, total_return=0.03),
                                      "source": "estimated_benchmark"} for name in ("rule", "buy_hold")}
                       for part in ("validation", "test")}}


@pytest.mark.parametrize("url", [
    "http://public.example.com", "https://localhost", "https://127.0.0.1", "https://[::1]",
    "https://10.0.0.1", "https://169.254.169.254", "https://api", "https://oracle.local",
    "https://127.1", "https://0177.0.0.1", "https://public..example.com", "https://public\n.example.com",
    "https://user:secret@public.example.com", "https://public.example.com/?token=secret",
    "https://public.example.com/#fragment", "https://public.example.com/api",
])
def test_cloud_frontend_refuses_unsafe_backend_origins(url):
    with pytest.raises(ValueError):
        DashboardSettings(api_url=url)


def test_local_frontend_preserves_private_docker_and_loopback_support():
    assert validated_backend_url("http://127.0.0.1:8000/") == "http://127.0.0.1:8000"
    assert validated_backend_url("http://api:8000") == "http://api:8000"
    with pytest.raises(ValueError, match="HTTPS"):
        validated_backend_url("http://unsecured.public.example.com")


def test_cloud_secrets_cannot_override_https_or_include_trading_keys():
    settings = cloud_settings({"papertrade": {"api_url": "https://paper-api.example.com"}})
    assert settings.require_https
    assert not hasattr(settings, "api_token")
    with pytest.raises(ValueError):
        cloud_settings({"papertrade": {"api_url": "https://paper-api.example.com", "require_https": False}})
    with pytest.raises(ValueError):
        cloud_settings({"papertrade": {"api_url": "https://paper-api.example.com", "groq_api_key": "fixture-only"}})


def test_missing_cloud_backend_has_no_local_fallback_and_exposes_no_secret(monkeypatch):
    def no_http(**kwargs):
        raise AssertionError("A bad cloud configuration must never make a network request")
    monkeypatch.setattr(httpx, "Client", no_http)
    app = AppTest.from_file(ROOT / "cloud_dashboard/streamlit_app.py")
    app.secrets["papertrade"] = {"api_url": "http://127.0.0.1:8000", "password": "must-never-display"}
    app.run()
    assert not app.exception
    assert app.error
    assert "must-never-display" not in app.error[0].value
    assert "persistent backend host" in app.error[0].value
    assert "Do not add trading or AI credentials to Community Cloud" in app.error[0].value
    assert "Oracle" not in app.error[0].value
    assert not app.text_input


def cloud_app(monkeypatch):
    requests = []
    original_client = httpx.Client

    def backend(request):
        requests.append(request)
        assert request.url.scheme == "https" and request.url.host == "paper-api.example.com"
        if request.url.path == "/auth/login":
            return httpx.Response(200, json={"access_token": "fixture-session-token"})
        assert request.headers["Authorization"] == "Bearer fixture-session-token"
        if request.url.path == "/status":
            return httpx.Response(200, json={"online": False, "mode": "paper", "execution": "simulator",
                "open_positions": [], "ai": {"provider": "groq", "model": "fixture-configured-model",
                                             "status": "unavailable"},
                "strategy": {"mode": "quant_only", "execution_enabled": False}})
        if request.url.path == "/tables/ai_analyses":
            return httpx.Response(200, json={"rows": [{"id": 1, "symbol": "BTC/USD", "provider": "groq",
                "status": "valid", "model": "fixture-configured-model", "data_timestamp": "2026-11-05T12:00:00Z",
                "latency_ms": 123, "total_tokens": 345, "response": {"recommendation": "NO_TRADE",
                "reasoning_summary": "Fixture evidence does not justify an entry.",
                "supporting_factors": ["No confirmed edge"], "risk_factors": ["Provider uncertainty"]}}]})
        if request.url.path == "/tables/strategy_validations":
            return httpx.Response(200, json={"rows": [
                {"id": number, "strategy": strategy, "source": "forward_replay", "accepted": False,
                 "report": comparison_report()} for number, strategy in enumerate(("hybrid", "quant_only"), start=1)]})
        return httpx.Response(200, json={"rows": []})

    monkeypatch.setattr(httpx, "Client", lambda **kwargs: original_client(
        transport=httpx.MockTransport(backend), **kwargs))
    app = AppTest.from_file(ROOT / "cloud_dashboard/streamlit_app.py")
    app.secrets["papertrade"] = {"api_url": "https://paper-api.example.com"}
    app.run()
    assert not app.exception and requests == []
    app.text_input[0].set_value("admin")
    app.text_input[1].set_value("fixture-password")
    app.button[0].click().run()
    assert not app.exception
    return app, requests


def test_cloud_dashboard_preserves_auth_and_displays_only_recorded_ai_data(monkeypatch):
    app, requests = cloud_app(monkeypatch)
    app.radio[0].set_value("AI analysis").run()
    assert not app.exception
    assert "Fixture evidence does not justify an entry." in [element.value for element in app.text]
    paths = {request.url.path for request in requests}
    assert {"/tables/ai_analyses", "/tables/ai_requests", "/tables/strategy_observations"} <= paths
    assert app.dataframe[0].value.iloc[0]["response.recommendation"] == "NO_TRADE"


def test_resume_does_not_hide_disabled_strategy_execution_warning(monkeypatch):
    app, requests = cloud_app(monkeypatch)
    assert any("validated strategy is explicitly enabled" in item.value for item in app.warning)
    app.radio[0].set_value("Controls").run()
    next(button for button in app.button if button.label == "Resume paper trading").click().run()
    assert not app.exception
    assert any("Resume only clears a pause" in item.value for item in app.warning)
    actions = [json.loads(request.content) for request in requests if request.url.path == "/controls"]
    assert actions == [{"action": "resume"}]


def test_cloud_dashboard_keeps_strategy_result_sources_separate(monkeypatch):
    app, _ = cloud_app(monkeypatch)
    app.radio[0].set_value("Strategy comparison").run()
    assert not app.exception
    frames = [frame.value for frame in app.dataframe if "result_kind" in frame.value]
    assert [frame.partition.unique().tolist() for frame in frames] == [["validation"], ["test"], ["research_only"]]
    assert all(frame.source.unique().tolist() == ["forward_replay"] for frame in frames)
    assert all(len(frame) == 5 for frame in frames[:2])  # Three strategies plus two benchmarks, once each.
    assert set(frames[0].result_kind) == {"estimated_strategy", "estimated_benchmark"}
    assert not app.metric  # UI does not combine backtests and account performance.


def test_comparison_transform_deduplicates_certificate_reports_and_preserves_actual_values():
    records = [{"source": "forward_replay", "strategy": name, "report": comparison_report()}
               for name in ("quant_only", "ai_filtered_quant", "hybrid")]
    result = comparison_metrics(records)
    assert len(result) == 11
    quant_test = result.loc[(result.strategy == "quant_only") & (result.partition == "test")].iloc[0]
    assert quant_test.total_return == -0.10 and quant_test.trade_count == 7 and quant_test.transaction_costs == 12.34
    assert set(result.loc[result.result_kind == "estimated_benchmark"].strategy) == {"rule", "buy_hold"}
    research = result.loc[result.strategy == "ai_only_research"].iloc[0]
    assert pd.isna(research.total_return) and pd.isna(research.trade_count)


def test_comparison_transform_keeps_sources_and_distinct_periods_separate():
    first = comparison_report()
    other = comparison_report()
    other["source"] = "backtest"
    result = comparison_metrics([{"source": "forward_replay", "report": first},
                                 {"source": "backtest", "report": other}])
    assert len(result) == 22 and set(result.source) == {"forward_replay", "backtest"}
    later = comparison_report()
    later["split"]["test"]["end"] = "2026-01-05"
    assert len(comparison_metrics([{"report": first}, {"report": later}])) == 22


def test_empty_comparison_reports_do_not_invent_performance():
    assert comparison_metrics([]).empty
    assert comparison_metrics([{"source": "forward_replay", "report": {}}]).empty
    assert comparison_metrics([{"source": "forward_replay", "report": None}]).empty


def test_cloud_token_is_never_reused_after_backend_origin_changes(monkeypatch):
    app, requests = cloud_app(monkeypatch)
    count = len(requests)
    app.secrets["papertrade"] = {"api_url": "https://different-backend.example.com"}
    app.run()
    assert not app.exception
    assert len(requests) == count
    assert "Backend changed" in app.error[0].value


def test_cloud_dependency_list_does_not_install_engine_or_ml():
    requirements = (ROOT / "cloud_dashboard/requirements.txt").read_text().lower()
    assert all(name not in requirements for name in ("lightgbm", "sqlalchemy", "alembic", "apscheduler", "-e ."))
    # Exercise a fresh process so imports performed by other tests do not affect this contract.
    subprocess.run([sys.executable, "-c", "import sys; import papertrade.dashboard; "
        "assert not any(name in sys.modules for name in "
        "('lightgbm','sqlalchemy','papertrade.engine','papertrade.brokers.alpaca'))"], check=True)
