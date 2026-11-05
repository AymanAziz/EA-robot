"""Independent, deterministic long-only risk approval across every configured account."""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime

from papertrade.config import Settings
from papertrade.domain import INSTRUMENTS, Instrument, Position, Quote


@dataclass(frozen=True)
class Portfolio:
    equity: float
    cash: float
    daily_start_equity: float
    peak_equity: float
    positions: list[Position]
    reserved_exposure: float = 0
    reserved_positions: int = 0
    reconciled: bool = False
    broker_cash: dict[str, float] = field(default_factory=dict)
    reserved_by_group: dict[str, float] = field(default_factory=dict)
    reserved_symbols: frozenset[str] = frozenset()


@dataclass(frozen=True)
class RiskContext:
    now: datetime
    candle_at: datetime
    quote: Quote
    market_open: bool
    model_valid: bool
    protected: bool
    volume: float
    atr: float
    killed: bool = False
    paused: bool = False
    daily_circuit: bool = False
    broker_cash: float | None = None
    session_remaining_ok: bool = True


@dataclass(frozen=True)
class RiskApproval:
    approved: bool
    reason: str
    qty: float = 0
    stop_loss: float | None = None
    take_profit: float | None = None


def approve_entry(instrument: Instrument, portfolio: Portfolio, ctx: RiskContext,
                  settings: Settings) -> RiskApproval:
    def deny(reason):
        return RiskApproval(False, reason)

    if ctx.killed:
        return deny("kill_switch")
    if ctx.paused:
        return deny("paused")
    if not portfolio.reconciled:
        return deny("reconciliation_incomplete")
    if not ctx.market_open:
        return deny("market_closed")
    if not ctx.session_remaining_ok:
        return deny("session_closes_before_horizon")
    if not ctx.model_valid:
        return deny("model_invalid")
    if not ctx.protected:
        return deny("protection_unavailable")
    numeric = [portfolio.equity, portfolio.cash, portfolio.daily_start_equity,
               portfolio.peak_equity, portfolio.reserved_exposure, ctx.atr, ctx.quote.bid,
               ctx.quote.ask, ctx.volume]
    if not all(math.isfinite(x) for x in numeric) or ctx.atr <= 0 or ctx.quote.bid <= 0:
        return deny("invalid_numeric_input")
    if portfolio.equity <= 0 or portfolio.daily_start_equity <= 0 or portfolio.peak_equity <= 0:
        return deny("invalid_equity")
    if ctx.quote.ask < ctx.quote.bid or not ctx.quote.tradeable:
        return deny("invalid_quote")
    if not 0 <= (ctx.now - ctx.quote.timestamp).total_seconds() <= settings.max_quote_age_seconds:
        return deny("stale_quote")
    age = (ctx.now - ctx.candle_at).total_seconds()
    if age < 900:
        return deny("incomplete_candle")
    if age > settings.max_data_age_seconds:
        return deny("stale_data")
    if ctx.quote.spread_bps > instrument.max_spread_bps:
        return deny("excessive_spread")
    if ctx.volume < instrument.min_volume:
        return deny("insufficient_liquidity")
    if ctx.daily_circuit or portfolio.equity <= portfolio.daily_start_equity * (1 - settings.daily_loss_limit):
        return deny("daily_loss_circuit")
    if portfolio.equity <= portfolio.peak_equity * (1 - settings.max_drawdown):
        return deny("maximum_drawdown")
    if any(p.symbol not in INSTRUMENTS or p.qty < 0 or not math.isfinite(p.qty * p.current_price)
           or p.current_price <= 0 for p in portfolio.positions):
        return deny("unsupported_position")
    if any(p.symbol == instrument.symbol and p.qty != 0 for p in portfolio.positions):
        return deny("averaging_disabled")
    if instrument.symbol in portfolio.reserved_symbols:
        return deny("pending_order_for_symbol")
    count = sum(p.qty != 0 for p in portfolio.positions) + portfolio.reserved_positions
    if count >= settings.max_positions:
        return deny("position_limit")

    capital = min(portfolio.equity, settings.capital)
    notional = sum(abs(p.qty * p.current_price) for p in portfolio.positions)
    group_exposure = sum(abs(p.qty * p.current_price) for p in portfolio.positions
                         if INSTRUMENTS[p.symbol].correlation_group == instrument.correlation_group)
    group_exposure += portfolio.reserved_by_group.get(instrument.correlation_group, 0)
    broker_cash = ctx.broker_cash if ctx.broker_cash is not None else portfolio.cash
    available_cash = min(portfolio.cash, broker_cash) - portfolio.reserved_exposure
    if not math.isfinite(available_cash) or available_cash <= 0:
        return deny("insufficient_cash")
    max_notional = min(
        capital * settings.max_total_exposure - notional - portfolio.reserved_exposure,
        capital * min(instrument.max_exposure, settings.max_instrument_exposure),
        capital * settings.max_correlated_exposure - group_exposure,
        available_cash,
    )
    if max_notional <= 0:
        return deny("exposure_limit")
    entry = ctx.quote.ask * (1 + instrument.slippage_bps / 10000)
    stop_distance = ctx.atr * instrument.stop_atr
    # Include estimated entry/exit friction in the risk budget; stops may gap further.
    friction = entry * (2 * instrument.fee_bps + 2 * instrument.slippage_bps + ctx.quote.spread_bps) / 10000
    quantity = min(capital * settings.risk_per_trade / (stop_distance + friction),
                   max_notional / (entry * (1 + instrument.fee_bps / 10000)))
    if instrument.market != "forex":
        # Forex provider volume is tick count, not executable base-currency units.
        quantity = min(quantity, ctx.volume * 0.01)
    quantity = math.floor(quantity / instrument.qty_step + 1e-9) * instrument.qty_step
    stop = ctx.quote.bid - stop_distance
    target = ctx.quote.ask + stop_distance * instrument.reward_risk
    if quantity < instrument.min_qty or stop <= 0:
        return deny("size_below_minimum_or_invalid_stop")
    return RiskApproval(True, "approved", round(quantity, 9), stop, target)
