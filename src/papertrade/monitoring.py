from __future__ import annotations

import math
from datetime import datetime

import numpy as np
from sqlalchemy import select

from papertrade.db import Database, aware
from papertrade.domain import utcnow
from papertrade.models import (AIAnalysisRow, FillRow, Health, InstrumentRow, ModelVersion,
                               PortfolioSnapshot, PositionRow, Run, StrategyValidation)


def performance(snapshots, fills):
    if not snapshots:
        return {}
    values = np.asarray([s.equity for s in snapshots], dtype=float)
    # Daily observations avoid annualizing one-minute monitoring samples as independent 15m returns.
    daily = {}
    for row in snapshots:
        daily[aware(row.timestamp).date()] = row.equity
    daily_values = np.asarray(list(daily.values()))
    returns = np.diff(daily_values) / daily_values[:-1] if len(daily_values) > 1 else np.array([])
    closed = [f for f in fills if f.side == "sell"]
    pnl = [f.realized_pl for f in closed if f.realized_pl is not None]
    wins, losses = sum(p for p in pnl if p > 0), -sum(p for p in pnl if p < 0)
    downside = returns[returns < 0]
    sharpe = float(returns.mean() / returns.std(ddof=1) * np.sqrt(365)) if len(returns) >= 20 and returns.std() > 0 else None
    sortino = float(returns.mean() / np.sqrt(np.mean(np.minimum(returns, 0) ** 2)) * np.sqrt(365)) if len(returns) >= 20 and len(downside) > 1 else None
    by_market = {}
    from papertrade.domain import INSTRUMENTS
    for fill in closed:
        market = INSTRUMENTS[fill.symbol].market if fill.symbol in INSTRUMENTS else "external"
        if fill.realized_pl is not None:
            by_market[market] = by_market.get(market, 0) + fill.realized_pl
    return {"total_return": float(values[-1] / values[0] - 1) if values[0] else None,
            "win_rate": sum(p > 0 for p in pnl) / len(pnl) if pnl else None,
            "profit_factor": wins / losses if losses else None,
            "sharpe": sharpe if sharpe is None or math.isfinite(sharpe) else None,
            "sortino": sortino if sortino is None or math.isfinite(sortino) else None,
            "max_drawdown": max(s.max_drawdown for s in snapshots),
            "trade_count": len(closed), "fees_reported": sum(f.fee for f in fills),
            "fees_final": all(f.fees_final for f in fills), "by_market": by_market,
            "realized_pl_complete": all(f.realized_pl is not None for f in closed),
            "method": "Daily observed equity (20+ returns); FIFO net closed fill P/L; missing basis unavailable; fees may be provisional"}


def system_status(db: Database, now: datetime | None = None):
    now = now or utcnow()
    with db.session() as session:
        health = list(session.scalars(select(Health)))
        runs = session.scalars(select(Run).where(Run.status == "success").order_by(Run.id.desc())).first()
        snapshots = list(session.scalars(select(PortfolioSnapshot).order_by(PortfolioSnapshot.id)))
        positions = list(session.scalars(select(PositionRow).where(PositionRow.closed_at.is_(None))))
        fills = list(session.scalars(select(FillRow)))
        models = list(session.scalars(select(ModelVersion)))
        instruments = list(session.scalars(select(InstrumentRow).where(InstrumentRow.enabled.is_(True))))
        latest_ai = session.scalar(select(AIAnalysisRow).where(AIAnalysisRow.status == "valid").order_by(AIAnalysisRow.id.desc()))
        validations = session.scalars(select(StrategyValidation).order_by(StrategyValidation.id.desc()).limit(50)).all()
    last = snapshots[-1] if snapshots else None
    def recent(row, age):
        return 0 <= (now - aware(row.timestamp)).total_seconds() <= age
    brokers = [h for h in health if h.name.startswith("broker:")]
    active_brokers = [h for h in brokers if h.status != "disabled"]
    data = {h.name.split(":", 1)[1]: h for h in health if h.name.startswith("data:")}
    usable_data = [data[i.symbol] for i in instruments if i.symbol in data and data[i.symbol].status != "disabled"]
    all_data_observed = all(i.symbol in data and recent(data[i.symbol], 1200) for i in instruments)
    scheduler = next((h for h in health if h.name == "scheduler"), None)
    watchdog = next((h for h in health if h.name == "watchdog"), None)
    online = bool(scheduler and scheduler.status == "ok" and recent(scheduler, 1200)
                  and active_brokers and all(h.status == "ok" and recent(h, 120) for h in active_brokers)
                  and all_data_observed and usable_data
                  and watchdog and watchdog.status == "ok" and recent(watchdog, 120)
                  and all(h.status in {"ok", "closed"} and recent(h, 1200) for h in usable_data))
    from papertrade.engine import candle_slot
    from datetime import timedelta
    next_run = candle_slot(now) + timedelta(seconds=20)
    if next_run <= now:
        next_run += timedelta(minutes=15)
    from papertrade.ai.budget import UsageBudget
    from papertrade.ai.service import model_for, provider_disabled_reason
    from papertrade.host_health import observe_host
    ai_reason = provider_disabled_reason(db.settings)
    ai_health = {h.name: {"status": h.status, "detail": h.detail, "timestamp": aware(h.timestamp).isoformat()}
                 for h in health if h.name.startswith("ai:") or h.name == "ai_worker"}
    reconcile_health = next((h for h in health if h.name == "reconciliation"), None)
    provider_status = {}
    for provider in ("groq", "hermes"):
        item = ai_health.get(f"ai:{provider}")
        provider_status[provider] = (item if item else {"status": "disabled" if provider != db.settings.ai_provider or ai_reason else "not_probed",
            "detail": "Optional provider not selected" if provider != db.settings.ai_provider else ai_reason or "No provider connectivity verified"})
    return {"online": online, "mode": "paper", "execution": db.settings.execution,
            "paused": db.control("paused", False), "killed": db.control("killed", False),
            "close_requested": db.control("close_requested", False),
            "daily_circuit": db.control("daily_circuit"), "drawdown_circuit": db.control("drawdown_circuit", False),
            "heartbeat": aware(scheduler.timestamp).isoformat() if scheduler else None,
            "last_success": aware(runs.finished_at).isoformat() if runs and runs.finished_at else None,
            "next_run": next_run.isoformat(),
            "equity": last.equity if last else None, "cash": last.cash if last else None,
            "unrealized_pl": last.unrealized_pl if last else None,
            "realized_pl": last.realized_pl if last else None, "daily_pl": last.daily_pl if last else None,
            "max_drawdown": last.max_drawdown if last else None,
            "open_positions": len(positions),
            "brokers": {h.name: {"status": h.status, "detail": h.detail, "timestamp": aware(h.timestamp).isoformat()} for h in brokers},
            "models": [{"symbol": m.symbol, "version": m.version, "accepted": m.accepted, "active": m.active} for m in models],
            "metrics": performance(snapshots, fills),
            "last_reconciliation": aware(reconcile_health.timestamp).isoformat() if reconcile_health and reconcile_health.status == "ok" else None,
            "ai": {"provider": db.settings.ai_provider, "model": model_for(db.settings) or None,
                   "enabled": db.settings.ai_enabled, "configuration_status": "disabled" if ai_reason else "configured_not_certified",
                   "reason": ai_reason, "providers": provider_status,
                   "last_success": aware(latest_ai.created_at).isoformat() if latest_ai else None,
                   "usage": UsageBudget(db).metrics(now), "confidence_is_calibrated": False},
            "strategy": {"mode": db.settings.strategy, "execution_enabled": db.settings.strategy_execution_enabled,
                "validations": [{"id": v.id, "symbol": v.symbol, "strategy": v.strategy, "accepted": v.accepted,
                                 "approved": v.approved, "source": v.source} for v in validations]},
            "system_health": observe_host(db)}
