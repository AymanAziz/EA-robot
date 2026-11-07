from __future__ import annotations

import math
from datetime import datetime, time, timedelta, timezone

import numpy as np
from sqlalchemy import case, func, select

from papertrade.db import Database, aware
from papertrade.domain import utcnow
from papertrade.models import (AIAnalysisRow, FillRow, Health, InstrumentRow, ModelVersion,
                               PortfolioSnapshot, PositionRow, Run, StrategyValidation)


def _daily_closing_equities(session, first_at, last_at):
    """Read one indexed closing snapshot per UTC day, without scanning minute rows."""
    values = []
    day = aware(first_at).date()
    final_day = aware(last_at).date()
    while day <= final_day:
        start = datetime.combine(day, time.min, tzinfo=timezone.utc)
        end = start + timedelta(days=1)
        value = session.scalar(select(PortfolioSnapshot.equity)
            .where(PortfolioSnapshot.timestamp >= start, PortfolioSnapshot.timestamp < end)
            .order_by(PortfolioSnapshot.timestamp.desc(), PortfolioSnapshot.id.desc()).limit(1))
        if value is not None:
            values.append(value)
        day += timedelta(days=1)
    return np.asarray(values, dtype=float)


def _stored_performance(session, last):
    """Calculate status metrics without materializing minute snapshots or fill history."""
    if last is None:
        return {}
    first_at, first_equity = session.execute(select(PortfolioSnapshot.timestamp, PortfolioSnapshot.equity)
        .order_by(PortfolioSnapshot.id).limit(1)).one()
    daily_values = _daily_closing_equities(session, first_at, last.timestamp)
    returns = np.diff(daily_values) / daily_values[:-1] if len(daily_values) > 1 else np.array([])
    downside = returns[returns < 0]
    sharpe = float(returns.mean() / returns.std(ddof=1) * np.sqrt(365)) if len(returns) >= 20 and returns.std() > 0 else None
    sortino = float(returns.mean() / np.sqrt(np.mean(np.minimum(returns, 0) ** 2)) * np.sqrt(365)) if len(returns) >= 20 and len(downside) > 1 else None

    fill_count, fees_reported, provisional_fees = session.execute(select(
        func.count(FillRow.id), func.coalesce(func.sum(FillRow.fee), 0.0),
        func.coalesce(func.sum(case((FillRow.fees_final.is_(False), 1), else_=0)), 0))).one()
    closed_count, pnl_count, positive_count, wins, losses = session.execute(select(
        func.count(FillRow.id),
        func.count(FillRow.realized_pl),
        func.coalesce(func.sum(case((FillRow.realized_pl > 0, 1), else_=0)), 0),
        func.coalesce(func.sum(case((FillRow.realized_pl > 0, FillRow.realized_pl), else_=0.0)), 0.0),
        func.coalesce(func.sum(case((FillRow.realized_pl < 0, -FillRow.realized_pl), else_=0.0)), 0.0),
    ).where(FillRow.side == "sell")).one()
    from papertrade.domain import INSTRUMENTS
    by_market = {}
    realized_by_symbol = session.execute(select(FillRow.symbol, func.sum(FillRow.realized_pl))
        .where(FillRow.side == "sell", FillRow.realized_pl.is_not(None)).group_by(FillRow.symbol)).all()
    for symbol, realized_pl in realized_by_symbol:
        market = INSTRUMENTS[symbol].market if symbol in INSTRUMENTS else "external"
        by_market[market] = by_market.get(market, 0) + realized_pl
    return {"total_return": float(last.equity / first_equity - 1) if first_equity else None,
            "win_rate": positive_count / pnl_count if pnl_count else None,
            "profit_factor": wins / losses if losses else None,
            "sharpe": sharpe if sharpe is None or math.isfinite(sharpe) else None,
            "sortino": sortino if sortino is None or math.isfinite(sortino) else None,
            "max_drawdown": last.max_drawdown,
            "trade_count": closed_count, "fees_reported": fees_reported,
            "fees_final": not provisional_fees if fill_count else True, "by_market": by_market,
            "realized_pl_complete": pnl_count == closed_count,
            "method": "Daily observed equity (20+ returns); FIFO net closed fill P/L; missing basis unavailable; fees may be provisional"}


def system_status(db: Database, now: datetime | None = None):
    now = now or utcnow()
    with db.session() as session:
        health = list(session.scalars(select(Health)))
        runs = session.scalars(select(Run).where(Run.status == "success").order_by(Run.id.desc())).first()
        last = session.scalar(select(PortfolioSnapshot).order_by(PortfolioSnapshot.id.desc()).limit(1))
        positions = list(session.scalars(select(PositionRow).where(PositionRow.closed_at.is_(None))))
        metrics = _stored_performance(session, last)
        models = list(session.scalars(select(ModelVersion)))
        instruments = list(session.scalars(select(InstrumentRow).where(InstrumentRow.enabled.is_(True))))
        latest_ai = session.scalar(select(AIAnalysisRow).where(AIAnalysisRow.status == "valid").order_by(AIAnalysisRow.id.desc()))
        validations = session.scalars(select(StrategyValidation).order_by(StrategyValidation.id.desc()).limit(50)).all()
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
            "metrics": metrics,
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
