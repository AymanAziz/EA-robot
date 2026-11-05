"""One serialized execution path for analysis, monitoring and administrative actions.

Durable intent is committed before the network request. Uncertain requests reserve
capital indefinitely until a broker lookup confirms their outcome. No POST retries.
"""
from __future__ import annotations

import hashlib
import logging
import math
from dataclasses import asdict
from datetime import datetime, timedelta
from typing import Callable

from filelock import FileLock, Timeout
from sqlalchemy import func, or_, select
from sqlalchemy.dialects.sqlite import insert

from papertrade.config import Settings
from papertrade.db import Database, aware
from papertrade.decisions import decide
from papertrade.domain import INSTRUMENTS, Account, Broker, BrokerOrder, OrderRejected, OrderRequest, utcnow
from papertrade.logging import redact
from papertrade.models import (AuditLog, Control, FillRow, Health, InstrumentRow, OrderRow, PortfolioSnapshot,
                               PositionRow, PredictionRow, RiskEvent, Run, SignalRow, StrategyObservation)
from papertrade.risk import Portfolio, RiskContext, approve_entry

log = logging.getLogger(__name__)
TERMINAL = {"filled", "canceled", "cancelled", "expired", "rejected", "replaced", "abandoned"}


def candle_slot(now: datetime) -> datetime:
    return now.replace(minute=(now.minute // 15) * 15, second=0, microsecond=0)


class TradingEngine:
    def __init__(self, settings: Settings, db: Database, brokers: dict[str, Broker] | None = None,
                 sources: dict[str, object] | None = None, predictor: Callable | None = None,
                 clock: Callable = utcnow, ai_service=None):
        self.settings, self.db = settings, db
        with db.session() as session:
            session.execute(insert(Control).values(key="execution_mode", value=settings.execution).on_conflict_do_nothing())
            if session.get(Control, "execution_mode").value != settings.execution:
                from papertrade.domain import BrokerError
                raise BrokerError("Execution venue changed; use an isolated database and state directory")
        settings.state_dir.mkdir(parents=True, exist_ok=True)
        self.lock = FileLock(settings.state_dir / "engine.lock")
        self.clock = clock
        self.sources = sources if sources is not None else self._sources()
        self.disabled = {}
        if brokers is None:
            from papertrade.brokers.factory import build_brokers
            brokers, self.disabled = build_brokers(settings, quote_provider=self._quote,
                                                  data_provider=self._market_data)
        self.brokers = brokers
        if predictor is None:
            from papertrade.ml import predict
            predictor = predict
        self.predictor = predictor
        from papertrade.ai.service import AIService
        self.ai_service = ai_service if ai_service is not None else AIService(settings, db, clock=clock)
        self.accounts: dict[str, Account] = {}
        self.positions = []
        self.open_orders = []
        self.portfolio: Portfolio | None = None

    def _sources(self):
        from papertrade.data import CoinbaseData
        sources = {"crypto": CoinbaseData()}
        if self.settings.alpaca_key.get_secret_value() and self.settings.alpaca_secret.get_secret_value():
            from papertrade.brokers.alpaca import AlpacaPaper
            sources["equity"] = AlpacaPaper(self.settings.alpaca_key.get_secret_value(),
                                             self.settings.alpaca_secret.get_secret_value())
            # Broker-hosted crypto execution uses that broker's own market feed.
            if self.settings.execution == "brokers":
                sources["crypto"] = sources["equity"]
        if self.settings.oanda_token.get_secret_value() and self.settings.oanda_account_id.get_secret_value():
            from papertrade.brokers.oanda import OandaPractice
            sources["forex"] = OandaPractice(self.settings.oanda_token.get_secret_value(),
                                               self.settings.oanda_account_id.get_secret_value())
        return sources

    def _quote(self, symbol):
        source = self.sources.get(INSTRUMENTS[symbol].market)
        if source is None:
            raise RuntimeError("market_data_credentials_missing")
        return source.get_quote(symbol)

    def _market_data(self, symbol, start, end):
        source = self.sources.get(INSTRUMENTS[symbol].market)
        if source is None:
            raise RuntimeError("market_data_credentials_missing")
        return source.get_market_data(symbol, start, end)

    def _broker(self, symbol):
        return self.brokers.get("simulator" if self.settings.execution == "simulator"
                                else INSTRUMENTS[symbol].broker)

    def _error(self, exc):
        # Provider adapters sanitize their own public errors. Never persist arbitrary repr/traceback.
        from papertrade.domain import BrokerError
        from papertrade.data import DataError
        from papertrade.ml import ModelError
        if isinstance(exc, (BrokerError, DataError, ModelError)):
            return redact(str(exc), self.settings)[:250]
        return type(exc).__name__

    def event(self, kind, detail, symbol=None):
        with self.db.session() as session:
            session.add(RiskEvent(kind=kind, detail=redact(detail, self.settings), symbol=symbol))
        log.warning("%s symbol=%s detail=%s", kind, symbol, redact(detail, self.settings))

    def _record_order(self, broker: str, order: BrokerOrder):
        client_id = order.client_order_id or f"external-{broker}-{order.id}"
        with self.db.session() as session:
            row = session.scalar(select(OrderRow).where(OrderRow.broker == broker, or_(
                OrderRow.client_order_id == client_id, OrderRow.broker_order_id == order.id)))
            if row is None:
                # Include broker protective/manual orders so dashboard/recovery sees actual account activity.
                row = OrderRow(client_order_id=client_id,
                    broker=broker, broker_order_id=order.id, symbol=order.symbol,
                    side=order.side, action="BUY" if order.side == "buy" else "SELL", qty=order.qty,
                    reference_price=order.filled_avg_price or 0)
                session.add(row)
            row.broker_order_id, row.status = order.id, order.status.lower()
            row.filled_qty, row.filled_avg_price, row.fees = order.filled_qty, order.filled_avg_price, order.fees
            row.updated_at = utcnow()

    def reconcile(self, now=None) -> bool:
        now = now or self.clock()
        accounts, positions, open_orders = {}, [], []
        success = bool(self.brokers)
        for name, reason in self.disabled.items():
            self.db.health(f"broker:{name}", "disabled", reason, now)
        for name, broker in self.brokers.items():
            try:
                account = broker.get_account()
                if account.currency != "USD" or not account.trading_allowed:
                    from papertrade.domain import BrokerError
                    raise BrokerError("Unsupported account currency or paper account disabled")
                if account.identity:
                    previous_identity = self.db.control(f"account_identity:{name}")
                    if previous_identity and previous_identity != account.identity:
                        from papertrade.domain import BrokerError
                        raise BrokerError("Paper account changed; use isolated state before resuming")
                    self.db.set_control(f"account_identity:{name}", account.identity)
                if not all(math.isfinite(v) for v in (account.equity, account.cash)) or account.equity <= 0:
                    raise RuntimeError("invalid_account")
                broker_positions = broker.get_positions()
                broker_orders = broker.get_open_orders()
                with self.db.session() as session:
                    pending = session.scalars(select(OrderRow).where(OrderRow.broker == name,
                                                      OrderRow.status.not_in(TERMINAL))).all()
                for row in pending:
                    if row.status == "prepared":
                        # Only an intent whose send marker was never committed is definitely unsent.
                        with self.db.session() as session:
                            session.get(OrderRow, row.id).status = "abandoned"
                        continue
                    found = broker.get_order_status(row.broker_order_id) if row.broker_order_id else broker.find_order(row.client_order_id)
                    if found is not None:
                        self._record_order(name, found)
                    else:
                        with self.db.session() as session:
                            session.get(OrderRow, row.id).status = "uncertain"
                        success = False
                for order in broker_orders:
                    self._record_order(name, order)
                with self.db.session() as session:
                    cursor = session.get(Control, f"fills_cursor:{name}")
                    since = datetime.fromisoformat(cursor.value) - timedelta(days=1) if cursor else None
                fills = broker.get_fills(since)
                # Status polling may observe a fill that happened after the earlier position read.
                # Re-read holdings before dropping terminal order reservations.
                broker_positions = broker.get_positions()
                account = broker.get_account()
                broker_orders = broker.get_open_orders()
                if account.currency != "USD" or not account.trading_allowed:
                    raise RuntimeError("unsupported_currency_or_account_disabled")
                if (len({p.symbol for p in broker_positions}) != len(broker_positions) or
                    any(p.qty <= 0 or p.symbol not in INSTRUMENTS or
                        not all(math.isfinite(v) for v in (p.qty, p.current_price, p.avg_entry, p.unrealized_pl))
                        or p.current_price <= 0 for p in broker_positions)):
                    raise RuntimeError("unsupported_position_or_hedged_account")
                for order in broker_orders:
                    self._record_order(name, order)
                with self.db.session() as session:
                    for fill in fills:
                        session.execute(insert(FillRow).values(broker=name, broker_fill_id=fill.id,
                            broker_order_id=fill.order_id, symbol=fill.symbol, side=fill.side, qty=fill.qty,
                            price=fill.price, fee=fill.fee, realized_pl=fill.realized_pl,
                            fees_final=getattr(fill, "fees_final", True), timestamp=fill.timestamp
                            ).on_conflict_do_nothing(index_elements=["broker", "broker_fill_id"]))
                    # A historical cursor never jumps ahead of confirmed provider events.
                    if fills:
                        session.merge(Control(key=f"fills_cursor:{name}", value=max(f.timestamp for f in fills).isoformat()))
                    old = session.scalars(select(PositionRow).where(PositionRow.broker == name,
                                                                 PositionRow.closed_at.is_(None))).all()
                    live = {p.symbol: p for p in broker_positions if p.qty}
                    for row in old:
                        if row.symbol not in live:
                            row.closed_at, row.qty, row.updated_at = now, 0, now
                    for pos in live.values():
                        row = next((r for r in old if r.symbol == pos.symbol), None)
                        if row is None:
                            row = PositionRow(broker=name, symbol=pos.symbol, opened_at=now)
                            session.add(row)
                        row.qty, row.avg_entry = pos.qty, pos.avg_entry
                        row.current_price, row.unrealized_pl = pos.current_price, pos.unrealized_pl
                        row.updated_at = now
                accounts[name] = account
                positions.extend(broker_positions)
                open_orders.extend(broker_orders)
                self.db.health(f"broker:{name}", "ok", "Paper account and positions reconciled", now)
            except Exception as exc:
                success = False
                self.db.health(f"broker:{name}", "error", self._error(exc), now)
                self.event("broker_failure", f"{name}: {self._error(exc)}")
        self.accounts, self.positions, self.open_orders = accounts, positions, open_orders
        with self.db.session() as session:
            pending = session.scalars(select(OrderRow).where(OrderRow.status.not_in(TERMINAL))).all()
            if any(r.status in {"uncertain", "submitting"} or
                   (r.side == "buy" and (r.reference_price <= 0 or r.symbol not in INSTRUMENTS)) for r in pending):
                success = False
            prior_peak = session.scalar(select(func.max(PortfolioSnapshot.equity))) or 0
            prior_dd = session.scalar(select(func.max(PortfolioSnapshot.max_drawdown))) or 0
            latest_snapshot = session.scalar(select(PortfolioSnapshot).order_by(PortfolioSnapshot.id.desc()))
            midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
            prior_day = session.scalar(select(PortfolioSnapshot).where(PortfolioSnapshot.timestamp < midnight
                                            ).order_by(PortfolioSnapshot.id.desc()))
            from papertrade.ledger import update_realized
            all_fills = list(session.scalars(select(FillRow)))
            update_realized(all_fills)
            realized = (None if any(r.side == "sell" and r.realized_pl is None for r in all_fills)
                        else sum(r.realized_pl for r in all_fills if r.realized_pl is not None))
        equity = sum(a.equity for a in accounts.values())
        cash = sum(a.cash for a in accounts.values())
        complete = success and len(accounts) == len(self.brokers)
        day = now.date().isoformat()
        day_key = f"day_start:{day}"
        daily_start = self.db.control(day_key)
        # Conservative overnight baseline: last fully reconciled prior-day equity, or first actual observation.
        if daily_start is None and complete:
            daily_start = prior_day.equity if prior_day else equity
            self.db.set_control(day_key, daily_start)
        peak = max(prior_peak, equity, self.db.control("equity_peak", 0))
        reserved = [r for r in pending if r.side == "buy"]
        group_reserves = {}
        for row in reserved:
            item = INSTRUMENTS.get(row.symbol)
            if item:
                group_reserves[item.correlation_group] = group_reserves.get(item.correlation_group, 0) + row.qty * row.reference_price
        self.portfolio = Portfolio(equity, cash, daily_start or equity, peak, positions,
            reserved_exposure=sum(r.qty * r.reference_price for r in reserved),
            reserved_positions=len(reserved), reconciled=complete,
            broker_cash={name: a.cash for name, a in accounts.items()}, reserved_by_group=group_reserves,
            reserved_symbols=frozenset(r.symbol for r in pending))
        if complete:
            self.db.set_control("equity_peak", peak)
            drawdown = 1 - equity / peak if peak else 0
            max_dd = max(prior_dd, drawdown, self.db.control("observed_max_drawdown", 0))
            self.db.set_control("observed_max_drawdown", max_dd)
            if equity <= (daily_start or equity) * (1 - self.settings.daily_loss_limit):
                self.db.set_control("daily_circuit", day)
            if drawdown >= self.settings.max_drawdown:
                self.db.set_control("drawdown_circuit", True)
            if latest_snapshot is None or (now - aware(latest_snapshot.timestamp)).total_seconds() >= 60:
                with self.db.session() as session:
                    session.add(PortfolioSnapshot(timestamp=now, equity=equity, cash=cash,
                        unrealized_pl=sum(p.unrealized_pl for p in positions), realized_pl=realized,
                        daily_pl=equity - (daily_start or equity), max_drawdown=max_dd,
                        exposure=sum(abs(p.qty * p.current_price) for p in positions),
                        brokers={n: asdict(a) for n, a in accounts.items()}))
        self.db.health("reconciliation", "ok" if complete else "error",
                       "All configured paper accounts reconciled" if complete else "Paper reconciliation incomplete", now)
        return complete

    def _submit(self, name, request):
        broker = self.brokers[name]
        with self.db.session() as session:
            if session.scalar(select(OrderRow).where(OrderRow.client_order_id == request.client_order_id)):
                return False
            session.add(OrderRow(client_order_id=request.client_order_id, broker=name,
                symbol=request.symbol, action=request.action, side=request.side, qty=request.qty,
                reference_price=request.reference_price, stop_loss=request.stop_loss,
                take_profit=request.take_profit, status="prepared",
                expires_at=candle_slot(self.clock()) + timedelta(minutes=60) if request.side == "buy" else None))
        # Re-read durable controls immediately before submitting a new entry.
        with self.db.session() as session:
            instrument_enabled = session.get(InstrumentRow, request.symbol)
            instrument_enabled = bool(instrument_enabled and instrument_enabled.enabled)
        if request.side == "buy" and (self.db.control("paused") or self.db.control("killed") or
                                     self.db.control("close_requested") or not instrument_enabled):
            with self.db.session() as session:
                session.scalar(select(OrderRow).where(OrderRow.client_order_id == request.client_order_id)).status = "abandoned"
            return False
        with self.db.session() as session:
            session.scalar(select(OrderRow).where(OrderRow.client_order_id == request.client_order_id)).status = "submitting"
        try:
            response = broker.submit_order(request)
            self._record_order(name, response)
            return True
        except Exception as exc:
            with self.db.session() as session:
                row = session.scalar(select(OrderRow).where(OrderRow.client_order_id == request.client_order_id))
                row.status = "rejected" if isinstance(exc, OrderRejected) else "uncertain"
                row.error = self._error(exc)
            self.event("order_rejected" if isinstance(exc, OrderRejected) else "order_uncertain",
                       self._error(exc), request.symbol)
            # Do not retry: next reconciliation queries this exact client identifier.
            return False

    def _client_id(self, broker, symbol, at, action):
        digest = hashlib.sha256(f"{self.settings.execution}:{broker}:{symbol}:{at}:{action}".encode()).hexdigest()
        return "pt-" + digest[:40]

    def _close(self, position, now, reason):
        broker = self.brokers[position.broker]
        try:
            if not broker.is_market_open(position.symbol, now):
                self.event("exit_deferred", "market_closed", position.symbol)
                return False
            orders = [o for o in broker.get_open_orders() if o.symbol == position.symbol]
            for order in orders:
                broker.cancel_order(order.id)
            if any(o.symbol == position.symbol for o in broker.get_open_orders()):
                self.event("exit_deferred", "cancellation_not_confirmed", position.symbol)
                return False
            # Confirm cancellation in durable state before testing for outstanding intents.
            # Otherwise a protective leg recorded as accepted blocks its replacement exit.
            self.reconcile(self.clock())
            actual = next((p for p in broker.get_positions() if p.symbol == position.symbol), None)
            if actual is None or actual.qty <= 0:
                return False
            quote = broker.get_quote(position.symbol)
            current = self.clock()
            if not quote.tradeable or not -2 <= (current - quote.timestamp).total_seconds() <= self.settings.max_quote_age_seconds:
                self.event("exit_deferred", "stale_or_untradeable_quote", position.symbol)
                return False
            # A rejected/cancelled close may be attempted at a later monitoring minute with a new intent.
            at = now.replace(second=0, microsecond=0).isoformat()
            request = OrderRequest(position.symbol, "sell", actual.qty,
                self._client_id(position.broker, position.symbol, at, "CLOSE"), quote.bid, action="CLOSE")
            with self.db.session() as session:
                unresolved = session.scalar(select(OrderRow).where(OrderRow.broker == position.broker,
                    OrderRow.symbol == position.symbol, OrderRow.status.not_in(TERMINAL)))
            if unresolved:
                return False
            self.event("close_requested", reason, position.symbol)
            return self._submit(position.broker, request)
        except Exception as exc:
            self.event("exit_failure", self._error(exc), position.symbol)
            return False

    def _monitor_locked(self, now):
        self.reconcile(now)
        okay = True
        killed = self.db.control("killed", False)
        close_all = self.db.control("close_requested", False) or killed
        circuit = self.db.control("daily_circuit") == now.date().isoformat() or self.db.control("drawdown_circuit", False)
        if close_all:
            for name, broker in self.brokers.items():
                try:
                    for order in broker.get_open_orders():
                        broker.cancel_order(order.id)
                except Exception as exc:
                    okay = False
                    self.event("cancel_failure", self._error(exc))
        for position in list(self.positions):
            try:
                broker = self.brokers[position.broker]
                with self.db.session() as session:
                    entry = session.scalar(select(OrderRow).where(OrderRow.broker == position.broker,
                        OrderRow.symbol == position.symbol, OrderRow.side == "buy", OrderRow.filled_qty > 0
                        ).order_by(OrderRow.id.desc()))
                expired = bool(entry and entry.expires_at and now >= aware(entry.expires_at))
                if close_all or circuit or expired:
                    if not self._close(position, self.clock(), "holding_horizon" if expired else "kill_or_portfolio_circuit"):
                        okay = False
                elif position.broker == "simulator":
                    broker.process_protection(position.symbol, broker.get_quote(position.symbol))
                elif broker.supports_protection(position.symbol):
                    orders = broker.get_open_orders()
                    active = [o for o in orders if o.symbol == position.symbol and o.side == "sell" and
                              o.status not in {"held", "suspended", "pending_cancel", "pending_replace"}]
                    stop_qty = sum(o.qty for o in active if o.order_type in {"stop", "stop_limit", "trailing_stop"})
                    target_qty = sum(o.qty for o in active if o.order_type == "limit")
                    with self.db.session() as session:
                        partial = session.scalar(select(OrderRow).where(OrderRow.broker == position.broker,
                            OrderRow.symbol == position.symbol, OrderRow.side == "buy",
                            OrderRow.status.not_in(TERMINAL), OrderRow.filled_qty > 0))
                    if partial or stop_qty + 1e-9 < position.qty or target_qty + 1e-9 < position.qty:
                        self.event("hosted_protection_missing", "Missing active stop/target or incomplete bracket entry", position.symbol)
                        if not self._close(position, self.clock(), "hosted_protection_not_confirmed"):
                            okay = False
                elif not broker.supports_protection(position.symbol):
                    # Existing positions remain monitored even after entry authorization is disabled.
                    quote = broker.get_quote(position.symbol)
                    if not -2 <= (self.clock() - quote.timestamp).total_seconds() <= self.settings.max_quote_age_seconds:
                        raise RuntimeError("stale_protection_quote")
                    if entry is None or entry.stop_loss is None or entry.take_profit is None:
                        if not self._close(position, self.clock(), "protection_missing"):
                            okay = False
                    elif quote.bid <= entry.stop_loss or quote.bid >= entry.take_profit:
                        if not self._close(position, self.clock(), "monitored_stop_or_target"):
                            okay = False
            except Exception as exc:
                okay = False
                self.event("monitor_failure", self._error(exc), position.symbol)
        complete = self.reconcile(now)
        if close_all and complete and not self.positions and not self.open_orders:
            with self.db.session() as session:
                pending = session.scalar(select(OrderRow).where(OrderRow.status.not_in(TERMINAL)))
            if not pending:
                self.db.set_control("close_requested", False)
        self.db.health("monitor", "ok" if okay and complete else "error", "Protection monitoring cycle", now)
        return okay and complete

    def monitor_once(self, now=None):
        try:
            with self.lock.acquire(timeout=0):
                now = now or self.clock()
                result = self._monitor_locked(now)
                self.db.health("watchdog", "ok" if result else "error", "Independent minute monitor", now)
                url = self.settings.watchdog_url.get_secret_value()
                if url and result:
                    import httpx
                    try:
                        if not url.startswith("https://"):
                            raise ValueError("External heartbeat requires HTTPS")
                        from papertrade.monitoring import system_status
                        if system_status(self.db, now)["online"]:
                            response = httpx.get(url, timeout=10, follow_redirects=False, trust_env=False)
                            response.raise_for_status()
                            self.db.health("external_watchdog", "ok", "External heartbeat acknowledged", now)
                    except Exception:
                        self.db.health("external_watchdog", "error", "External heartbeat failed", now)
                return result
        except Timeout:
            return False

    def run_once(self, now=None):
        now = now or self.clock()
        try:
            with self.lock.acquire(timeout=0):
                return self._run_locked(now)
        except Timeout:
            return {"status": "skipped", "reason": "another_execution_is_running"}

    def _run_locked(self, now):
        slot = candle_slot(now).isoformat()
        complete = self.reconcile(now)
        with self.db.session() as session:
            existing = session.scalar(select(Run).where(Run.slot == slot))
            if existing:
                return {"status": "skipped", "reason": "slot_already_processed", "slot": slot}
            for interrupted in session.scalars(select(Run).where(Run.status == "running")):
                interrupted.status, interrupted.finished_at = "interrupted", now
            run = Run(slot=slot, started_at=now, status="running")
            session.add(run)
            session.flush()
            run_id = run.id
            enabled = {r.symbol: r.enabled for r in session.scalars(select(InstrumentRow))}
        outcomes, data_ok = {}, True
        try:
            # Every run checks protective exits even with missing models or paused new entries.
            self._monitor_locked(now)
            for symbol, instrument in INSTRUMENTS.items():
                broker = self._broker(symbol)
                if not enabled.get(symbol, False):
                    outcomes[symbol] = "market_disabled"
                    continue
                if broker is None:
                    outcomes[symbol] = "paper_broker_credentials_missing"
                    self.db.health(f"data:{symbol}", "disabled", outcomes[symbol], now)
                    continue
                if instrument.market not in self.sources:
                    outcomes[symbol] = "market_data_credentials_missing"
                    self.db.health(f"data:{symbol}", "disabled", outcomes[symbol], now)
                    continue
                try:
                    if not broker.is_market_open(symbol, now):
                        outcomes[symbol] = "market_closed"
                        self.db.health(f"data:{symbol}", "closed", "Market session closed", now)
                        continue
                    from papertrade.data import validate_candles
                    cached = self.db.load_candles(symbol, limit=600)
                    start = (cached.index[-1].to_pydatetime() - timedelta(hours=1)
                             if not cached.empty else now - timedelta(days=7))
                    fresh = self._market_data(symbol, start, now)
                    valid = validate_candles(fresh, now, instrument.market, require_fresh=True,
                                            max_age_seconds=self.settings.max_data_age_seconds)
                    self.db.store_candles(symbol, valid, type(self.sources[instrument.market]).__name__)
                    candles = self.db.load_candles(symbol, limit=600)
                    candles = validate_candles(candles, now, instrument.market, require_fresh=True,
                                               max_age_seconds=self.settings.max_data_age_seconds)
                    self.db.health(f"data:{symbol}", "ok", "Completed candles validated", now)
                    from papertrade.model_monitor import monitor_predictions
                    monitor_predictions(self.db, symbol, candles, now)
                    bar_at = candles.index[-1].to_pydatetime()
                    quote = broker.get_quote(symbol)
                    held = next((p for p in self.positions if p.symbol == symbol and p.broker == broker.name), None)
                    try:
                        prediction = self.predictor(candles, instrument, self.settings, now=now)
                        with self.db.session() as session:
                            session.execute(insert(PredictionRow).values(symbol=symbol, candle_at=bar_at,
                                model_version=prediction.model_version, probability=prediction.probability,
                                expected_return=prediction.expected_return, regime=prediction.regime
                                ).on_conflict_do_nothing())
                        self.db.health(f"model:{symbol}", "ok", prediction.model_version, now)
                    except Exception as exc:
                        self.db.health(f"model:{symbol}", "disabled", self._error(exc), now)
                        self._signal(symbol, bar_at, "HOLD", "model_unavailable_or_invalid")
                        outcomes[symbol] = "model_unavailable_or_invalid"
                        continue
                    decision = decide(prediction.probability, prediction.expected_return, prediction.regime,
                                      instrument, quote, float(candles.iloc[-1].volume), held.qty if held else 0,
                                      self.settings)
                    if decision.action == "BUY" and prediction.probability < getattr(prediction, "threshold", 0):
                        decision = type(decision)("HOLD", "below_validated_threshold", decision.cost_bps)
                    decision = self._fuse(decision, symbol, bar_at, prediction)
                    action, reason = decision.action, decision.reason
                    if action == "BUY":
                        # The preceding symbol's accepted order may already have changed both accounts and reserves.
                        self.reconcile(now)
                        # A slow provider must not allow an old quote or a run-start timestamp to approve risk.
                        quote = broker.get_quote(symbol)
                        decision_now = self.clock()
                        from papertrade.calendars import is_market_open
                        decision = decide(prediction.probability, prediction.expected_return, prediction.regime,
                            instrument, quote, float(candles.iloc[-1].volume), held.qty if held else 0, self.settings)
                        if decision.action == "BUY" and prediction.probability < getattr(prediction, "threshold", 0):
                            decision = type(decision)("HOLD", "below_validated_threshold", decision.cost_bps)
                        decision = self._fuse(decision, symbol, bar_at, prediction)
                        with self.db.session() as session:
                            monitor = session.get(Health, "watchdog")
                            external_watchdog = session.get(Health, "external_watchdog")
                        monitoring = bool(monitor and monitor.status == "ok" and
                            0 <= (decision_now - aware(monitor.timestamp)).total_seconds() <= 120)
                        protected = broker.supports_protection(symbol)
                        if broker.name == "simulator":
                            protected = protected and monitoring
                        if not protected:
                            protected = (self.settings.allow_unhosted_protection and monitoring
                                and bool(external_watchdog and external_watchdog.status == "ok" and
                                         0 <= (decision_now - aware(external_watchdog.timestamp)).total_seconds() <= 120))
                        approval = approve_entry(instrument, self.portfolio, RiskContext(
                            decision_now, bar_at, quote, broker.is_market_open(symbol, decision_now), True,
                            protected, float(candles.iloc[-1].volume), prediction.atr,
                            killed=self.db.control("killed", False),
                            paused=self.db.control("paused", False) or self.db.control("drawdown_circuit", False)
                                   or self.db.control("close_requested", False),
                            daily_circuit=self.db.control("daily_circuit") == now.date().isoformat(),
                            broker_cash=self.accounts.get(broker.name).cash if broker.name in self.accounts else 0,
                            session_remaining_ok=is_market_open(instrument.market, decision_now + timedelta(minutes=60))),
                            self.settings)
                        if not approval.approved or decision.action != "BUY":
                            action, reason = "HOLD", approval.reason if not approval.approved else decision.reason
                            self.event("risk_denied", reason, symbol)
                        else:
                            action, reason = decision.action, decision.reason
                            req = OrderRequest(symbol, "buy", approval.qty,
                                self._client_id(broker.name, symbol, bar_at.isoformat(), "BUY"), quote.ask,
                                approval.stop_loss, approval.take_profit)
                            self._submit(broker.name, req)
                    elif action == "CLOSE" and held:
                        self._close(held, now, "model_exit")
                    self._signal(symbol, bar_at, action, reason, prediction, decision.cost_bps)
                    outcomes[symbol] = f"{action}:{reason}"
                except Exception as exc:
                    data_ok = False
                    outcomes[symbol] = self._error(exc)
                    self.db.health(f"data:{symbol}", "error", self._error(exc), now)
                    self.event("analysis_failure", self._error(exc), symbol)
            complete = self.reconcile(now)
            status = "success" if complete and data_ok else "degraded"
        except Exception as exc:
            status = "failed"
            outcomes["error"] = self._error(exc)
            self.event("run_failure", self._error(exc))
        with self.db.session() as session:
            run = session.get(Run, run_id)
            run.status, run.finished_at, run.detail = status, now, outcomes
        self.db.health("scheduler", "ok" if status == "success" else "error", status, now)
        log.info("analysis_completed slot=%s status=%s", slot, status)
        return {"status": status, "slot": slot, "outcomes": outcomes}

    def _fuse(self, quant, symbol, candle_at, prediction):
        """Cache-only AI gate; no provider HTTP request can run under the execution lock."""
        from papertrade.ai.fusion import fuse_decision
        from papertrade.ai.service import model_for
        now = self.clock()
        cached, certificate = None, None
        if quant.action not in {"CLOSE", "SELL"}:
            try:
                cached = self.ai_service.cached(symbol, now=now)
                if self.settings.strategy in {"ai_filtered_quant", "hybrid"}:
                    certificate = self.ai_service.certificate(symbol, prediction.model_version)
            except Exception:
                cached, certificate = None, None
        decision = fuse_decision(quant, strategy=self.settings.strategy, symbol=symbol,
            candle_at=candle_at, now=now, quant_model_version=prediction.model_version,
            ai=cached.response if cached else None, ai_provider=self.settings.ai_provider,
            ai_model=model_for(self.settings), ai_created_at=aware(cached.created_at) if cached else None,
            certificate=certificate, settings=self.settings)
        values = dict(symbol=symbol, candle_at=candle_at, strategy=self.settings.strategy,
            decision_at=now, model_version=prediction.model_version, probability=prediction.probability,
            expected_return=prediction.expected_return, regime=prediction.regime, quant_action=quant.action,
            fused_action=decision.action, fusion_reason=decision.reason,
            ai_analysis_id=cached.id if cached else None, ai_response=cached.response if cached else None,
            ai_provider=self.settings.ai_provider, ai_model=model_for(self.settings),
            ai_created_at=aware(cached.created_at) if cached else None,
            ai_data_timestamp=aware(cached.data_timestamp) if cached else None,
            source="forward_observation", execution_venue="local_simulator" if self.settings.execution == "simulator" else "broker_paper")
        with self.db.session() as session:
            session.execute(insert(StrategyObservation).values(**values).on_conflict_do_update(
                index_elements=["symbol", "candle_at", "strategy"], set_=values))
        return decision

    def _signal(self, symbol, bar_at, action, reason, prediction=None, cost=0):
        with self.db.session() as session:
            session.execute(insert(SignalRow).values(symbol=symbol, market=INSTRUMENTS[symbol].market,
                candle_at=bar_at, action=action, reason=reason, probability=prediction.probability if prediction else None,
                estimated_cost_bps=cost, model_version=prediction.model_version if prediction else None,
                regime=prediction.regime if prediction else None).on_conflict_do_nothing())

    def control(self, action, market=None, actor="admin"):
        if action not in {"pause", "resume", "kill", "close_all", "enable_market", "disable_market"}:
            raise ValueError("Unknown action")
        if action.endswith("market") and market not in {"crypto", "equity", "forex"}:
            raise ValueError("Unknown market")
        # Kill latch commits immediately, even while a slow network call owns the execution lock.
        with self.db.session() as session:
            if action in {"kill", "pause", "close_all"}:
                session.merge(Control(key="paused", value=True))
            if action == "kill":
                session.merge(Control(key="killed", value=True))
            if action in {"kill", "close_all"}:
                session.merge(Control(key="close_requested", value=True))
            if action == "resume":
                session.merge(Control(key="paused", value=False))
                session.merge(Control(key="killed", value=False))
            if action in {"enable_market", "disable_market"}:
                for row in session.scalars(select(InstrumentRow).where(InstrumentRow.market == market)):
                    row.enabled = action == "enable_market"
            session.add(AuditLog(actor=actor, action=action, detail={"market": market}))
        if action in {"kill", "close_all"}:
            self.monitor_once()
        return {"action": action, "paused": self.db.control("paused"), "killed": self.db.control("killed"),
                "close_requested": self.db.control("close_requested"), "note": "Exits require broker confirmation"}
