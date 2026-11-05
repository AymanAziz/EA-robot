"""Authenticated Streamlit read model and control client; never writes the database."""
from __future__ import annotations

from typing import Any, Literal
import ipaddress
import hashlib
import json
import re
from urllib.parse import urlsplit

import httpx
import numpy as np
import pandas as pd
import streamlit as st
from pydantic import BaseModel, ConfigDict, Field, field_validator

from papertrade.config import Settings
from papertrade.domain import INSTRUMENTS


class DashboardUnavailable(RuntimeError):
    pass


def validated_backend_url(value: str, *, require_https: bool = False) -> str:
    """Keep user passwords/session tokens on an explicitly configured backend origin."""
    if not isinstance(value, str) or any(ord(character) <= 32 or ord(character) == 127 for character in value):
        raise ValueError("Invalid backend URL")
    try:
        parsed = urlsplit(value)
        host = (parsed.hostname or "").lower().rstrip(".")
        port = parsed.port
    except (ValueError, TypeError):
        raise ValueError("Invalid backend URL") from None
    if (not host or parsed.username or parsed.password or parsed.query or parsed.fragment
            or parsed.path not in {"", "/"} or parsed.scheme not in {"http", "https"}
            or port is not None and not 1 <= port <= 65535):
        raise ValueError("Configure a backend origin without credentials, paths, query or fragment")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
        if (not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", host)
                or any(not label or len(label) > 63 or label.startswith("-") or label.endswith("-")
                       for label in host.split("."))):
            raise ValueError("Invalid backend hostname") from None
    local_http = host in {"localhost", "127.0.0.1", "::1", "api"}
    if parsed.scheme == "http" and (require_https or not local_http):
        raise ValueError("External dashboard connections require HTTPS")
    if require_https and (host in {"localhost", "api"} or host.endswith((".localhost", ".local", ".internal"))
                          or address is not None and not address.is_global
                          or address is None and ("." not in host or not re.search(r"[a-z]", host.split(".")[-1]))):
        raise ValueError("Community Cloud needs a public HTTPS backend")
    return value.rstrip("/")


class DashboardSettings(BaseModel):
    """Community Cloud only knows a backend URL; trading and AI secrets stay on the VM."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    api_url: str
    dashboard_refresh_seconds: int = Field(30, ge=5, le=300)
    require_https: Literal[True] = True

    @field_validator("api_url")
    @classmethod
    def public_origin(cls, value):
        return validated_backend_url(value, require_https=True)


def cloud_settings(secrets: Any) -> DashboardSettings:
    values = dict(secrets["papertrade"])
    # Do not allow a secret to turn off HTTPS enforcement.
    if "require_https" in values:
        raise ValueError("Cloud HTTPS enforcement cannot be configured away")
    return DashboardSettings(**values)


def api_request(settings: Settings | DashboardSettings, method: str, path: str, **kwargs: Any) -> Any:
    """All reads and mutations cross the backend's authentication seam."""
    try:
        backend = validated_backend_url(settings.api_url, require_https=getattr(settings, "require_https", False))
    except ValueError:
        raise DashboardUnavailable("Backend configuration is invalid; remote connections require HTTPS.") from None
    if not path.startswith("/") or path.startswith("//") or "?" in path or "#" in path:
        raise DashboardUnavailable("Invalid backend request path.")
    token = st.session_state.get("auth_token", "")
    if token and st.session_state.get("auth_backend_url") != backend:
        st.session_state.pop("auth_token", None)
        st.session_state.pop("auth_backend_url", None)
        raise DashboardUnavailable("Backend changed or session expired. Sign in again.")
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    try:
        with httpx.Client(timeout=20, follow_redirects=False, trust_env=False) as client:
            response = client.request(method, backend + path,
                                      headers=headers, **kwargs)
        if response.status_code == 401:
            st.session_state.pop("auth_token", None)
            st.session_state.pop("auth_backend_url", None)
            raise DashboardUnavailable("Session expired or credentials were rejected. Sign in again.")
        if response.is_error or response.is_redirect:
            raise DashboardUnavailable(f"Backend request failed (HTTP {response.status_code}).")
        return response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise DashboardUnavailable("The backend is unavailable. Trading status is unknown.") from exc


def table_records(settings: Settings | DashboardSettings, name: str, limit: int = 500) -> list[dict]:
    payload = api_request(settings, "GET", f"/tables/{name}", params={"limit": limit})
    if isinstance(payload, dict):
        payload = payload.get("rows", payload.get("items", []))
    if not isinstance(payload, list) or not all(isinstance(item, dict) for item in payload):
        raise DashboardUnavailable("The backend returned invalid table data.")
    return payload


def rows(settings: Settings, name: str, limit: int = 500) -> pd.DataFrame:
    return pd.json_normalize(table_records(settings, name, limit))


def display_money(value: Any) -> str:
    try:
        number = float(value)
        return f"${number:,.2f}" if np.isfinite(number) else "—"
    except (TypeError, ValueError):
        return "—"


def performance(snapshots: pd.DataFrame, fills: pd.DataFrame) -> dict[str, Any]:
    """Descriptive statistics of stored paper fills, never advertised as a live edge."""
    result: dict[str, Any] = {}
    time_col = next((col for col in ("timestamp", "created_at", "as_of") if col in snapshots), None)
    if time_col and "equity" in snapshots:
        curve = snapshots.copy()
        curve[time_col] = pd.to_datetime(curve[time_col], utc=True, errors="coerce")
        curve["equity"] = pd.to_numeric(curve["equity"], errors="coerce")
        curve = curve.dropna(subset=[time_col, "equity"]).sort_values(time_col).set_index(time_col)
        curve = curve.loc[~curve.index.duplicated(keep="last")]
        if len(curve) > 1 and curve.equity.iloc[0] > 0:
            result["curve"] = curve[["equity"]]
            result["return"] = float(curve.equity.iloc[-1] / curve.equity.iloc[0] - 1)
            result["drawdown"] = float((curve.equity / curve.equity.cummax() - 1).min())
            daily = curve.equity.resample("1D").last().dropna().pct_change().dropna()
            if len(daily) >= 20 and daily.std(ddof=1) > 0:
                result["sharpe"] = float(daily.mean() / daily.std(ddof=1) * np.sqrt(365))
                downside = np.sqrt(np.minimum(daily, 0).pow(2).mean())
                if downside > 0:
                    result["sortino"] = float(daily.mean() / downside * np.sqrt(365))
    if not fills.empty and "realized_pl" in fills:
        closed = fills
        if "side" in closed:
            closed = closed.loc[closed.side.astype(str).str.lower().eq("sell")]
        pnl = pd.to_numeric(closed.realized_pl, errors="coerce").dropna()
        result["trade_count"] = len(pnl)
        if len(pnl):
            result["win_rate"] = float((pnl > 0).mean())
            loss = -pnl[pnl < 0].sum()
            if loss > 0:
                result["profit_factor"] = float(pnl[pnl > 0].sum() / loss)
    return result


def table(frame: pd.DataFrame) -> None:
    if frame.empty:
        st.info("No records yet.")
    else:
        st.dataframe(frame, width="stretch", hide_index=True)


def login(settings: Settings) -> None:
    st.title("Papertrade")
    st.caption("Automated research and execution · paper accounts only")
    with st.form("sign_in", clear_on_submit=True):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Sign in", type="primary")
    if submitted:
        try:
            payload = api_request(settings, "POST", "/auth/login",
                                  json={"username": username, "password": password})
            token = payload.get("access_token", "")
            if not token:
                raise DashboardUnavailable("Sign in could not be completed.")
            st.session_state.auth_token = token
            st.session_state.auth_backend_url = validated_backend_url(
                settings.api_url, require_https=getattr(settings, "require_https", False))
            st.rerun()
        except DashboardUnavailable as exc:
            st.error(str(exc))


def control(settings: Settings, action: str, market: str | None = None) -> None:
    payload = {"action": action}
    if market:
        payload["market"] = market
    try:
        api_request(settings, "POST", "/controls", json=payload)
        st.success(f"Recorded: {action.replace('_', ' ')}")
    except DashboardUnavailable as exc:
        st.error(str(exc))


def render_dashboard(settings: Settings) -> None:
    with st.sidebar:
        st.title("Papertrade")
        st.caption("USD · PAPER ONLY")
        section = st.radio("Workspace", ["Overview", "Market analysis", "Trade history",
                                        "Performance", "AI analysis", "Strategy comparison",
                                        "System monitoring", "System health", "Controls"])
        if st.button("Sign out"):
            st.session_state.pop("auth_token", None)
            st.session_state.pop("auth_backend_url", None)
            st.rerun()
        st.caption("The scheduler runs independently of this dashboard.")

    @st.fragment(run_every=settings.dashboard_refresh_seconds)
    def view() -> None:
        try:
            status = api_request(settings, "GET", "/status")
            st.title(section)
            online = status.get("online", False)
            st.caption(f"{'ONLINE' if online else 'OFFLINE / NOT READY'} · "
                       f"PAPER · {status.get('execution', 'unknown')} execution")
            if status.get("killed"):
                st.error("Emergency stop is active. New entries are blocked.")
            elif status.get("paused"):
                st.warning("New entries are paused. Reconciliation and protective exits continue.")
            if (status.get("strategy") or {}).get("execution_enabled") is False:
                st.warning("New entries are disabled until a validated strategy is explicitly enabled on the backend. "
                           "Resume only clears a pause; protective exits continue.")
            if section == "Overview":
                for group in [
                    [("Equity", "equity"), ("Cash", "cash"), ("Daily P/L", "daily_pl")],
                    [("Unrealized P/L", "unrealized_pl"), ("Realized P/L", "realized_pl")],
                ]:
                    for col, (label, key) in zip(st.columns(len(group)), group):
                        col.metric(label, display_money(status.get(key)))
                st.write({"Last heartbeat": status.get("heartbeat"),
                          "Last successful analysis": status.get("last_success"),
                          "Next scheduled analysis": status.get("next_run"),
                          "Maximum drawdown": status.get("max_drawdown")})
                st.subheader("Open positions")
                positions = status.get("open_positions", [])
                if isinstance(positions, list):
                    table(pd.json_normalize(positions))
                else:
                    active_positions = rows(settings, "positions")
                    if "closed_at" in active_positions:
                        active_positions = active_positions.loc[active_positions.closed_at.isna()]
                    table(active_positions)
                st.subheader("Equity")
                stats = performance(rows(settings, "portfolio_snapshots"), pd.DataFrame())
                if "curve" in stats:
                    st.line_chart(stats["curve"])
                else:
                    st.info("Equity history appears after successful account reconciliation.")
            elif section == "Market analysis":
                signals = rows(settings, "signals")
                if "market" not in signals and "symbol" in signals:
                    signals["market"] = signals.symbol.map(
                        lambda symbol: INSTRUMENTS[symbol].market if symbol in INSTRUMENTS else "unknown")
                for tab, market in zip(st.tabs(["Crypto", "Forex", "Equities"]),
                                       ["crypto", "forex", "equity"]):
                    with tab:
                        table(signals.loc[signals.market.eq(market)] if "market" in signals else signals)
                st.subheader("Model predictions")
                table(rows(settings, "predictions"))
                st.subheader("Model versions and validation")
                table(rows(settings, "model_versions"))
            elif section == "Trade history":
                st.subheader("Orders · submitted does not mean filled")
                table(rows(settings, "orders"))
                st.subheader("Confirmed fills")
                fills = rows(settings, "fills")
                if "fees_final" in fills and not fills.fees_final.all():
                    st.warning("Some provider fees are not final. Fill-based P/L remains provisional; "
                               "reconciled account equity is authoritative.")
                table(fills)
                st.subheader("Position history")
                table(rows(settings, "positions"))
            elif section == "Performance":
                snapshots = rows(settings, "portfolio_snapshots", 1000)
                fills = rows(settings, "fills", 1000)
                if "fees_final" in fills and not fills.fees_final.all():
                    st.warning("Unallocated provider fees make fill-based statistics provisional. "
                               "The equity curve uses reconciled account balances.")
                stats = performance(snapshots, fills)
                stored_metrics = status.get("metrics", {})
                for public_key, local_key in {
                    "total_return": "return", "max_drawdown": "drawdown", "win_rate": "win_rate",
                    "profit_factor": "profit_factor", "sharpe": "sharpe", "sortino": "sortino",
                    "trade_count": "trade_count",
                }.items():
                    if public_key in stored_metrics:
                        stats[local_key] = stored_metrics[public_key]
                st.caption("Descriptive paper results from stored records; partial closing fills count "
                           "separately. Risk statistics use daily equity and 365-day annualization; "
                           "insufficient history appears as unavailable.")
                if stored_metrics.get("method"):
                    st.caption(str(stored_metrics["method"]))
                if stored_metrics.get("fees_final") is False:
                    st.warning("Provider fee allocation is incomplete; fill statistics are provisional.")
                if stored_metrics.get("realized_pl_complete") is False:
                    st.warning("Some historical fills have no confirmed cost basis. Closing P/L statistics "
                               "cover known-basis fills only; reconciled equity remains authoritative.")
                if "curve" in stats:
                    st.line_chart(stats.pop("curve"))
                for label, key, percent in [
                    ("Cumulative return", "return", True), ("Maximum drawdown", "drawdown", True),
                    ("Win rate", "win_rate", True), ("Profit factor", "profit_factor", False),
                    ("Sharpe", "sharpe", False), ("Sortino", "sortino", False),
                    ("Closed fills", "trade_count", False),
                ]:
                    value = stats.get(key)
                    st.metric(label, "—" if value is None else
                              (f"{value:.2%}" if percent else f"{value:,.2f}"))
                if not fills.empty and "symbol" in fills:
                    fills["market"] = fills.symbol.map(
                        lambda symbol: INSTRUMENTS[symbol].market if symbol in INSTRUMENTS else "other")
                    numeric = [col for col in ("realized_pl", "fee", "fees") if col in fills]
                    if numeric:
                        for col in numeric:
                            fills[col] = pd.to_numeric(fills[col], errors="coerce")
                        st.subheader("Stored realized P/L and costs by market")
                        table(fills.groupby("market", as_index=False)[numeric].sum(min_count=1))
                if stored_metrics.get("by_market"):
                    st.subheader("Backend performance by market")
                    by_market = stored_metrics["by_market"]
                    if isinstance(by_market, dict):
                        if all(value is None or isinstance(value, (int, float)) for value in by_market.values()):
                            table(pd.DataFrame(list(by_market.items()), columns=["market", "realized_pl"]))
                        else:
                            table(pd.DataFrame.from_dict(by_market, orient="index").rename_axis("market").reset_index())
                    elif isinstance(by_market, list):
                        table(pd.json_normalize(by_market))
            elif section == "System monitoring":
                st.write({"Heartbeat": status.get("heartbeat"), "Brokers": status.get("brokers"),
                          "Models": status.get("models"), "Next run": status.get("next_run")})
                for label, name in [("Scheduler runs", "runs"), ("Data and broker health", "health"),
                                    ("Risk events", "risk_events"), ("Recent audit records", "audit_logs")]:
                    with st.expander(label, expanded=name == "runs"):
                        table(rows(settings, name))
            elif section == "AI analysis":
                render_ai_analysis(settings, status)
            elif section == "Strategy comparison":
                render_strategy_comparison(settings, status)
            elif section == "System health":
                st.caption("Backend observations determine engine health. This page reaching your browser "
                           "does not establish Oracle, scheduler, broker or provider availability.")
                system_health = status.get("system_health")
                if system_health:
                    st.json(system_health)
                else:
                    st.info("No server resource/host health report has been recorded.")
                st.write({"Last successful trading cycle": status.get("last_success"),
                          "Scheduler heartbeat": status.get("heartbeat"),
                          "Broker status": status.get("brokers"),
                          "AI status": status.get("ai")})
                table(rows(settings, "health"))
                with st.expander("Recent execution errors and risk events"):
                    table(rows(settings, "risk_events"))
            else:
                st.caption("Every action is authorized again by the backend and recorded in the audit log.")
                col1, col2 = st.columns(2)
                if col1.button("Pause new trades", width="stretch"):
                    control(settings, "pause")
                if col2.button("Resume paper trading", width="stretch"):
                    control(settings, "resume")
                if st.button("Emergency stop", type="primary", width="stretch"):
                    control(settings, "kill")
                st.caption("Stopping entries does not guarantee liquidation. Check broker-confirmed orders "
                           "and fills after closing positions.")
                if st.button("Close paper positions", width="stretch"):
                    control(settings, "close_all")
                for market in ("crypto", "equity", "forex"):
                    col1, col2 = st.columns(2)
                    if col1.button(f"Enable {market}", key=f"enable_{market}", width="stretch"):
                        control(settings, "enable_market", market)
                    if col2.button(f"Disable {market}", key=f"disable_{market}", width="stretch"):
                        control(settings, "disable_market", market)
                table(rows(settings, "controls"))
        except DashboardUnavailable as exc:
            st.error(str(exc))
            st.warning("OFFLINE / UNKNOWN — dashboard availability is not evidence of engine health.")

    view()


def render_ai_analysis(settings, status) -> None:
    st.caption("AI confidence is an uncalibrated opinion. Provider text cannot authorize orders or bypass risk.")
    ai_status = status.get("ai")
    if ai_status:
        st.json(ai_status)
    else:
        st.info("No AI provider status has been recorded. Missing credentials or access means no AI analysis.")
    analyses = rows(settings, "ai_analyses")
    if not analyses.empty:
        symbol = st.selectbox("Symbol", sorted(analyses.symbol.unique())) if "symbol" in analyses else None
        selected = analyses.loc[analyses.symbol.eq(symbol)] if symbol else analyses
        latest = selected.iloc[0]
        payload = latest.to_dict()
        for label, names in [
            ("Recommendation", ("response.recommendation", "recommendation")),
            ("Data timestamp", ("data_timestamp", "response.data_timestamp")),
            ("Reasoning", ("response.reasoning_summary", "reasoning_summary")),
            ("Supporting factors", ("response.supporting_factors", "supporting_factors")),
            ("Risk factors", ("response.risk_factors", "risk_factors")),
        ]:
            value = next((payload[name] for name in names if name in payload), None)
            if value is not None and not (isinstance(value, float) and not np.isfinite(value)):
                st.write(label)
                # External model output is displayed as text, never HTML or executable instructions.
                st.text("\n".join(str(item) for item in value) if isinstance(value, list) else str(value))
    table(analyses)
    st.subheader("Quantitative predictions")
    table(rows(settings, "predictions"))
    st.subheader("Fusion decisions and disagreement")
    st.caption("Observations are research decisions unless their recorded source explicitly identifies executed paper trades.")
    table(rows(settings, "strategy_observations"))
    st.subheader("Request latency, usage and errors")
    table(rows(settings, "ai_requests"))


COMPARISON_METRICS = ("total_return", "max_drawdown", "sharpe", "profit_factor", "trade_count", "transaction_costs")


def comparison_metrics(records: list[dict]) -> pd.DataFrame:
    """Tidy only persisted metrics; deduplicate reports repeated in per-strategy certificates."""
    output, seen = [], set()
    for record in records:
        report = record.get("report")
        if not isinstance(report, dict):
            continue
        source = record.get("source") or report.get("source") or "unclassified"
        if record.get("source") and report.get("source") and record["source"] != report["source"]:
            source = "provenance_mismatch"
        identity = {name: report.get(name) for name in ("observations_sha256", "policy_sha256", "split",
            "quant_model_version", "ai_provider", "ai_model")}
        if not identity["observations_sha256"]:
            identity["report_sha256"] = hashlib.sha256(json.dumps(report, sort_keys=True, default=str).encode()).hexdigest()
        digest = hashlib.sha256(json.dumps(identity, sort_keys=True, default=str).encode()).hexdigest()
        key = (str(source), digest)
        if key in seen:
            continue
        seen.add(key)

        def add(partition, strategy, kind, metrics, *, accepted=None, reason=None, benchmark_source=None):
            period = report.get("split", {}).get(partition, {})
            entry = {"source": source, "evidence_id": digest[:12], "partition": partition,
                "period_start": period.get("start"), "period_end": period.get("end"),
                "strategy": strategy, "result_kind": kind, "benchmark_source": benchmark_source,
                "accepted": accepted, "reason": reason}
            for name in COMPARISON_METRICS:
                value = metrics.get(name) if isinstance(metrics, dict) else None
                entry[name] = value if isinstance(value, (int, float)) and not isinstance(value, bool) and np.isfinite(value) else None
            output.append(entry)

        strategies = report.get("strategies", {})
        if isinstance(strategies, dict):
            for name in ("quant_only", "ai_filtered_quant", "hybrid"):
                result = strategies.get(name)
                if not isinstance(result, dict):
                    continue
                for partition in ("validation", "test"):
                    part = result.get(partition)
                    if isinstance(part, dict) and isinstance(part.get("metrics"), dict):
                        add(partition, name, "estimated_strategy", part["metrics"], accepted=result.get("accepted"))
            research = strategies.get("ai_only_research")
            if isinstance(research, dict):
                add("research_only", "ai_only_research", "no_execution_or_performance", None,
                    accepted=False, reason=research.get("reason") or "Research only; performance unavailable")
        benchmarks = report.get("benchmarks", {})
        if isinstance(benchmarks, dict):
            for partition in ("validation", "test"):
                group = benchmarks.get(partition)
                if isinstance(group, dict):
                    for name in ("rule", "buy_hold"):
                        result = group.get(name)
                        if isinstance(result, dict) and isinstance(result.get("metrics"), dict):
                            add(partition, name, "estimated_benchmark", result["metrics"],
                                benchmark_source=result.get("source"))
    return pd.DataFrame(output)


def render_strategy_comparison(settings, status) -> None:
    st.caption("Result sources are kept separate. An observation or hypothetical recommendation is not an executed trade.")
    strategy = status.get("strategy")
    if strategy:
        st.json(strategy)
    records = table_records(settings, "strategy_validations")
    metrics = comparison_metrics(records)
    if not records:
        st.info("No strategy comparison has been validated. No performance figures are inferred from AI confidence.")
    elif metrics.empty:
        st.info("Stored validation records contain no comparable metrics yet; raw provenance remains available below.")
    else:
        for (source, partition), frame in metrics.groupby(["source", "partition"], dropna=False, sort=False):
            st.subheader(f"{source} · {partition}")
            if source == "forward_replay":
                st.caption("Estimated fills from genuine timestamped forward observations. This is not broker-confirmed P/L.")
            elif source in {"unclassified", "provenance_mismatch"}:
                st.warning("These records lack consistent source provenance and cannot establish validated performance.")
            if partition == "research_only":
                st.info("AI-only is research-only: execution is disabled and performance metrics are unavailable.")
            else:
                st.caption("Strategy and benchmark rows retain their recorded validation/test period. "
                           "Returns and drawdown are fractions; costs are denominated in account currency.")
            table(frame)
    if records:
        with st.expander("Raw validation records and approval provenance"):
            table(pd.json_normalize(records))
    st.subheader("Forward observations")
    st.caption("These are forward research/decision records. They are not combined with historical backtests or broker P/L.")
    table(rows(settings, "strategy_observations"))


def main(*, cloud: bool = False) -> None:
    st.set_page_config(page_title="Papertrade", page_icon="📊", layout="wide")
    try:
        settings = cloud_settings(st.secrets) if cloud else Settings()
        validated_backend_url(settings.api_url, require_https=cloud)
    except (ValueError, KeyError, FileNotFoundError):
        st.error("Configure the public HTTPS backend URL in Community Cloud Secrets under [papertrade]. "
                 "Trading and AI credentials belong on the Oracle VM.")
        st.stop()
    if cloud:
        st.caption("Streamlit Community Cloud dashboard · engine and persistent trading state remain on Oracle")
    if not st.session_state.get("auth_token"):
        login(settings)
    else:
        render_dashboard(settings)


if __name__ == "__main__":
    main()
