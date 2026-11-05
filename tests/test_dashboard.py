"""Dashboard calculations consume stored observations; they never invent a history."""
from pathlib import Path

import pandas as pd
import httpx
from streamlit.testing.v1 import AppTest

from papertrade.dashboard import display_money, performance


def test_empty_paper_history_has_no_performance_claim():
    assert performance(pd.DataFrame(), pd.DataFrame()) == {}
    assert display_money(None) == "—"


def test_stored_curve_and_confirmed_exits_define_displayed_metrics():
    snapshots = pd.DataFrame({
        "timestamp": ["2026-01-01T00:00:00Z", "2026-01-02T00:00:00Z", "2026-01-03T00:00:00Z"],
        "equity": [10000, 11000, 9000],
    })
    fills = pd.DataFrame({"side": ["buy", "sell", "sell"], "realized_pl": [0, 100, -50]})
    result = performance(snapshots, fills)
    assert round(result["return"], 4) == -0.10
    assert round(result["drawdown"], 4) == -0.1818
    assert result["profit_factor"] == 2
    assert result["win_rate"] == 0.5
    assert result["trade_count"] == 2
    assert "sharpe" not in result  # Three days cannot support an annualized risk claim.


def test_dashboard_requires_login_before_loading_private_records(monkeypatch):
    requests = []
    original_client = httpx.Client

    def backend(request):
        requests.append(request)
        if request.url.path == "/auth/login":
            return httpx.Response(200, json={"access_token": "test-session-bearer"})
        assert request.headers["Authorization"] == "Bearer test-session-bearer"
        if request.url.path == "/status":
            return httpx.Response(200, json={"online": False, "mode": "paper", "execution": "simulator",
                                              "paused": True, "open_positions": [], "equity": 10000,
                                              "metrics": {"trade_count": 2, "by_market": {"crypto": 50}}})
        return httpx.Response(200, json=[])

    transport = httpx.MockTransport(backend)
    monkeypatch.setattr(httpx, "Client", lambda **kwargs: original_client(transport=transport, **kwargs))
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "src/papertrade/dashboard.py").run()
    assert not app.exception
    assert requests == []
    app.text_input[0].set_value("admin")
    app.text_input[1].set_value("a-test-password")
    app.button[0].click().run()
    assert not app.exception
    assert app.title[0].value == "Overview"
    assert any(request.url.path == "/status" for request in requests)
    assert app.metric[0].value == "$10,000.00"
    app.radio[0].set_value("Performance").run()
    assert not app.exception
    assert app.dataframe[0].value.to_dict("records") == [{"market": "crypto", "realized_pl": 50}]
