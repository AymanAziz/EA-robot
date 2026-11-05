"""Persistent facts, not broker promises. Pending orders reserve portfolio capacity."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from papertrade.domain import utcnow


class Base(DeclarativeBase):
    pass


class InstrumentRow(Base):
    __tablename__ = "instruments"
    symbol: Mapped[str] = mapped_column(String, primary_key=True)
    market: Mapped[str] = mapped_column(String)
    broker: Mapped[str] = mapped_column(String)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class Candle(Base):
    __tablename__ = "candles"
    __table_args__ = (UniqueConstraint("symbol", "timestamp"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(ForeignKey("instruments.symbol"), index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    open: Mapped[float] = mapped_column(Float)
    high: Mapped[float] = mapped_column(Float)
    low: Mapped[float] = mapped_column(Float)
    close: Mapped[float] = mapped_column(Float)
    volume: Mapped[float] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String)


class FeatureMetadata(Base):
    __tablename__ = "feature_metadata"
    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    version: Mapped[str] = mapped_column(String)
    columns: Mapped[dict[str, Any]] = mapped_column(JSON)


class ModelVersion(Base):
    __tablename__ = "model_versions"
    __table_args__ = (UniqueConstraint("symbol", "version"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String, index=True)
    version: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    accepted: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=False)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class PredictionRow(Base):
    __tablename__ = "predictions"
    __table_args__ = (UniqueConstraint("symbol", "candle_at", "model_version"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String, index=True)
    candle_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    model_version: Mapped[str] = mapped_column(String)
    probability: Mapped[float] = mapped_column(Float)
    expected_return: Mapped[float] = mapped_column(Float)
    regime: Mapped[str] = mapped_column(String)


class SignalRow(Base):
    __tablename__ = "signals"
    __table_args__ = (UniqueConstraint("symbol", "candle_at"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String, index=True)
    market: Mapped[str] = mapped_column(String)
    candle_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    action: Mapped[str] = mapped_column(String)
    reason: Mapped[str] = mapped_column(String)
    probability: Mapped[float | None] = mapped_column(Float, nullable=True)
    estimated_cost_bps: Mapped[float] = mapped_column(Float, default=0)
    model_version: Mapped[str | None] = mapped_column(String, nullable=True)
    regime: Mapped[str | None] = mapped_column(String, nullable=True)


class OrderRow(Base):
    __tablename__ = "orders"
    __table_args__ = (UniqueConstraint("broker", "broker_order_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    client_order_id: Mapped[str] = mapped_column(String, unique=True)
    broker: Mapped[str] = mapped_column(String, index=True)
    broker_order_id: Mapped[str | None] = mapped_column(String, nullable=True)
    symbol: Mapped[str] = mapped_column(String)
    action: Mapped[str] = mapped_column(String)
    side: Mapped[str] = mapped_column(String)
    qty: Mapped[float] = mapped_column(Float)
    reference_price: Mapped[float] = mapped_column(Float)
    stop_loss: Mapped[float | None] = mapped_column(Float, nullable=True)
    take_profit: Mapped[float | None] = mapped_column(Float, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String, default="prepared", index=True)
    filled_qty: Mapped[float] = mapped_column(Float, default=0)
    filled_avg_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    fees: Mapped[float] = mapped_column(Float, default=0)
    error: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class FillRow(Base):
    __tablename__ = "fills"
    __table_args__ = (UniqueConstraint("broker", "broker_fill_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    broker: Mapped[str] = mapped_column(String)
    broker_fill_id: Mapped[str] = mapped_column(String)
    broker_order_id: Mapped[str] = mapped_column(String, index=True)
    symbol: Mapped[str] = mapped_column(String)
    side: Mapped[str] = mapped_column(String)
    qty: Mapped[float] = mapped_column(Float)
    price: Mapped[float] = mapped_column(Float)
    fee: Mapped[float] = mapped_column(Float)
    fees_final: Mapped[bool] = mapped_column(Boolean, default=True)
    realized_pl: Mapped[float | None] = mapped_column(Float, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PositionRow(Base):
    __tablename__ = "positions"
    id: Mapped[int] = mapped_column(primary_key=True)
    broker: Mapped[str] = mapped_column(String, index=True)
    symbol: Mapped[str] = mapped_column(String)
    qty: Mapped[float] = mapped_column(Float)
    avg_entry: Mapped[float] = mapped_column(Float)
    current_price: Mapped[float] = mapped_column(Float)
    unrealized_pl: Mapped[float] = mapped_column(Float)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PortfolioSnapshot(Base):
    __tablename__ = "portfolio_snapshots"
    id: Mapped[int] = mapped_column(primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    equity: Mapped[float] = mapped_column(Float)
    cash: Mapped[float] = mapped_column(Float)
    unrealized_pl: Mapped[float] = mapped_column(Float)
    realized_pl: Mapped[float | None] = mapped_column(Float, nullable=True)
    daily_pl: Mapped[float] = mapped_column(Float)
    max_drawdown: Mapped[float] = mapped_column(Float)
    exposure: Mapped[float] = mapped_column(Float)
    brokers: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class RiskEvent(Base):
    __tablename__ = "risk_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    symbol: Mapped[str | None] = mapped_column(String, nullable=True)
    kind: Mapped[str] = mapped_column(String)
    detail: Mapped[str] = mapped_column(String)


class Run(Base):
    __tablename__ = "runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    slot: Mapped[str] = mapped_column(String, unique=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String, default="running")
    detail: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class Health(Base):
    __tablename__ = "health"
    name: Mapped[str] = mapped_column(String, primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    status: Mapped[str] = mapped_column(String)
    detail: Mapped[str] = mapped_column(String)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    actor: Mapped[str] = mapped_column(String)
    action: Mapped[str] = mapped_column(String)
    detail: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class Control(Base):
    __tablename__ = "controls"
    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[Any] = mapped_column(JSON)


class AIAnalysisRow(Base):
    __tablename__ = "ai_analyses"
    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String, index=True)
    provider: Mapped[str] = mapped_column(String)
    model: Mapped[str] = mapped_column(String)
    context_hash: Mapped[str] = mapped_column(String, index=True)
    state_hash: Mapped[str] = mapped_column(String)
    quant_model_version: Mapped[str] = mapped_column(String)
    data_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String)
    response: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    context: Mapped[dict[str, Any]] = mapped_column(JSON)
    latency_ms: Mapped[float] = mapped_column(Float, default=0)
    prompt_tokens: Mapped[int | None] = mapped_column(nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(nullable=True)
    total_tokens: Mapped[int | None] = mapped_column(nullable=True)
    error: Mapped[str | None] = mapped_column(String, nullable=True)


class AIRequest(Base):
    __tablename__ = "ai_requests"
    id: Mapped[int] = mapped_column(primary_key=True)
    provider: Mapped[str] = mapped_column(String, index=True)
    model: Mapped[str] = mapped_column(String)
    symbol: Mapped[str | None] = mapped_column(String, nullable=True)
    day: Mapped[str] = mapped_column(String, index=True)
    kind: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String)
    reserved_tokens: Mapped[int] = mapped_column(default=0)
    charged_tokens: Mapped[int] = mapped_column(default=0)
    prompt_tokens: Mapped[int | None] = mapped_column(nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(nullable=True)
    total_tokens: Mapped[int | None] = mapped_column(nullable=True)
    latency_ms: Mapped[float] = mapped_column(Float, default=0)
    http_status: Mapped[int | None] = mapped_column(nullable=True)
    error: Mapped[str | None] = mapped_column(String, nullable=True)
    rate_limits: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class StrategyValidation(Base):
    __tablename__ = "strategy_validations"
    id: Mapped[int] = mapped_column(primary_key=True)
    strategy: Mapped[str] = mapped_column(String)
    symbol: Mapped[str] = mapped_column(String, index=True)
    quant_model_version: Mapped[str] = mapped_column(String)
    provider: Mapped[str] = mapped_column(String)
    ai_model: Mapped[str] = mapped_column(String)
    policy_hash: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    accepted: Mapped[bool] = mapped_column(Boolean, default=False)
    approved: Mapped[bool] = mapped_column(Boolean, default=False)
    source: Mapped[str] = mapped_column(String)
    report: Mapped[dict[str, Any]] = mapped_column(JSON)
    certificate: Mapped[dict[str, Any]] = mapped_column(JSON)


class StrategyObservation(Base):
    __tablename__ = "strategy_observations"
    __table_args__ = (UniqueConstraint("symbol", "candle_at", "strategy"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String, index=True)
    candle_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    decision_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    model_version: Mapped[str] = mapped_column(String)
    probability: Mapped[float] = mapped_column(Float)
    expected_return: Mapped[float] = mapped_column(Float)
    regime: Mapped[str] = mapped_column(String)
    strategy: Mapped[str] = mapped_column(String)
    quant_action: Mapped[str] = mapped_column(String)
    fused_action: Mapped[str] = mapped_column(String)
    fusion_reason: Mapped[str] = mapped_column(String)
    ai_analysis_id: Mapped[int | None] = mapped_column(ForeignKey("ai_analyses.id"), nullable=True)
    ai_response: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    ai_provider: Mapped[str] = mapped_column(String, default="")
    ai_model: Mapped[str] = mapped_column(String, default="")
    ai_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ai_data_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source: Mapped[str] = mapped_column(String)
    execution_venue: Mapped[str] = mapped_column(String)


TABLES = {cls.__tablename__: cls for cls in (
    InstrumentRow, Candle, FeatureMetadata, ModelVersion, PredictionRow, SignalRow, OrderRow,
    FillRow, PositionRow, PortfolioSnapshot, RiskEvent, Run, Health, AuditLog, Control,
    AIAnalysisRow, AIRequest, StrategyValidation, StrategyObservation
)}
