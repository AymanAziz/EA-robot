"""Transactional local paper ledger using real externally supplied quotes.

This is explicitly a local simulator, never a claimed broker connection. Stops are
software monitored and fill at the next observed bid, including adverse gaps.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
import hashlib
import math
from pathlib import Path
import sqlite3
import uuid

import pandas as pd

from papertrade.domain import Account, BrokerError, BrokerOrder, Fill, INSTRUMENTS
from papertrade.domain import OrderRejected, OrderRequest, Position, Quote, utcnow
from ._http import timestamp, validate_request


class LocalPaperSimulator:
    name = "simulator"

    def __init__(self, path: Path | str, capital: float = 10000, *, quote_provider=None, data_provider=None,
                 clock=utcnow):
        if not math.isfinite(capital) or capital <= 0:
            raise ValueError("Simulator capital must be finite and positive")
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.quote_provider = quote_provider
        self.data_provider = data_provider
        self.clock = clock
        with self._connect() as conn:
            if conn.execute("PRAGMA user_version").fetchone()[0] > 1:
                raise BrokerError("Simulator ledger schema is newer than this application")
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS account (
                    id INTEGER PRIMARY KEY CHECK(id=1), cash REAL NOT NULL, capital REAL NOT NULL,
                    identity TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS positions (
                    symbol TEXT PRIMARY KEY, qty REAL NOT NULL CHECK(qty>0), avg_entry REAL NOT NULL,
                    entry_fee REAL NOT NULL, stop_loss REAL, take_profit REAL);
                CREATE TABLE IF NOT EXISTS quotes (
                    symbol TEXT PRIMARY KEY, bid REAL NOT NULL, ask REAL NOT NULL,
                    timestamp TEXT NOT NULL, tradeable INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS orders (
                    id TEXT PRIMARY KEY, client_order_id TEXT NOT NULL UNIQUE, symbol TEXT NOT NULL,
                    side TEXT NOT NULL, qty REAL NOT NULL, status TEXT NOT NULL,
                    filled_qty REAL NOT NULL, filled_avg_price REAL, fees REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS fills (
                    id TEXT PRIMARY KEY, order_id TEXT NOT NULL UNIQUE REFERENCES orders(id),
                    symbol TEXT NOT NULL, side TEXT NOT NULL, qty REAL NOT NULL, price REAL NOT NULL,
                    fee REAL NOT NULL, timestamp TEXT NOT NULL, realized_pl REAL NOT NULL);
            """)
            # Add a persistent ledger identity to v0 ledgers without resetting cash
            # or positions. A deleted/recreated ledger receives a new identity.
            conn.execute("BEGIN IMMEDIATE")
            columns = {row["name"] for row in conn.execute("PRAGMA table_info(account)")}
            if "identity" not in columns:
                conn.execute("ALTER TABLE account ADD COLUMN identity TEXT")
            conn.execute("INSERT OR IGNORE INTO account(id, cash, capital, identity) VALUES(1, ?, ?, ?)",
                         (capital, capital, uuid.uuid4().hex))
            conn.execute("UPDATE account SET identity=? WHERE identity IS NULL OR identity=''", (uuid.uuid4().hex,))
            conn.execute("PRAGMA user_version=1")

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=30000")
        try:
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    def set_quote(self, symbol: str, quote: Quote) -> None:
        if symbol not in INSTRUMENTS:
            raise BrokerError("Unsupported simulator instrument")
        if (not math.isfinite(quote.bid) or not math.isfinite(quote.ask)
                or quote.bid <= 0 or quote.ask < quote.bid or quote.timestamp.tzinfo is None):
            raise BrokerError("Invalid simulator quote")
        with self._connect() as conn:
            conn.execute("INSERT INTO quotes VALUES (?, ?, ?, ?, ?) ON CONFLICT(symbol) DO UPDATE SET "
                         "bid=excluded.bid, ask=excluded.ask, timestamp=excluded.timestamp, tradeable=excluded.tradeable",
                         (symbol, quote.bid, quote.ask, quote.timestamp.isoformat(), int(quote.tradeable)))

    def get_quote(self, symbol: str) -> Quote:
        if self.quote_provider is not None:
            quote = self.quote_provider(symbol)
            self.set_quote(symbol, quote)
            return quote
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM quotes WHERE symbol=?", (symbol,)).fetchone()
        if row is None:
            raise BrokerError("No real quote is available for this simulator instrument")
        return Quote(row["bid"], row["ask"], timestamp(row["timestamp"]), bool(row["tradeable"]))

    def get_positions(self) -> list[Position]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM positions ORDER BY symbol").fetchall()
        result = []
        for row in rows:
            q = self.get_quote(row["symbol"])
            # Conservative liquidation mark; not a promise of achievable liquidation value.
            result.append(Position(row["symbol"], row["qty"], row["avg_entry"], q.bid, self.name,
                                   (q.bid - row["avg_entry"]) * row["qty"] - row["entry_fee"],
                                   row["stop_loss"], row["take_profit"]))
        return result

    def get_account(self) -> Account:
        positions = self.get_positions()
        with self._connect() as conn:
            row = conn.execute("SELECT cash, identity FROM account WHERE id=1").fetchone()
            cash = row["cash"]
            identity = hashlib.sha256(("simulator:" + row["identity"]).encode()).hexdigest()
        return Account(self.name, cash + sum(p.qty * p.current_price for p in positions), cash, identity=identity)

    def get_open_orders(self) -> list[BrokerOrder]:
        # Local market orders fill/reject atomically. No fictitious outstanding orders.
        return []

    def get_market_data(self, symbol: str, start: datetime, end: datetime) -> pd.DataFrame:
        if self.data_provider is None:
            raise BrokerError("Historical data source is not configured for simulator")
        return self.data_provider(symbol, start, end)

    @staticmethod
    def _order(row) -> BrokerOrder:
        return BrokerOrder(row["id"], row["client_order_id"], row["symbol"], row["side"], row["qty"],
                           row["status"], row["filled_qty"], row["filled_avg_price"], row["fees"],
                           order_type="market")

    def submit_order(self, order: OrderRequest) -> BrokerOrder:
        validate_request(order)
        if order.symbol not in INSTRUMENTS:
            raise OrderRejected("Unsupported simulator instrument")
        existing = self.find_order(order.client_order_id)
        if existing:
            return existing
        quote = self.get_quote(order.symbol)
        age = (self.clock() - quote.timestamp).total_seconds()
        if age > 60 or age < -2 or not quote.tradeable:
            raise OrderRejected("Fresh executable quote required for simulator fill")
        if not self.is_market_open(order.symbol, self.clock()):
            raise OrderRejected("Market is closed")
        spec = INSTRUMENTS[order.symbol]
        ratio = order.qty / spec.qty_step
        if order.qty < spec.min_qty or not math.isclose(ratio, round(ratio), rel_tol=1e-10, abs_tol=1e-7):
            raise OrderRejected("Order violates instrument quantity increment/minimum")
        price = ((quote.ask * (1 + spec.slippage_bps / 10000)) if order.side == "buy"
                 else (quote.bid * (1 - spec.slippage_bps / 10000)))
        fee = order.qty * price * spec.fee_bps / 10000
        identifier = "sim-" + order.client_order_id
        realized = 0.0
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            duplicate = conn.execute("SELECT * FROM orders WHERE client_order_id=?", (order.client_order_id,)).fetchone()
            if duplicate:
                return self._order(duplicate)
            position = conn.execute("SELECT * FROM positions WHERE symbol=?", (order.symbol,)).fetchone()
            cash = conn.execute("SELECT cash FROM account WHERE id=1").fetchone()[0]
            if order.side == "buy":
                if position:
                    raise OrderRejected("Adding to existing positions is disabled")
                if price * order.qty + fee > cash:
                    raise OrderRejected("Insufficient simulator cash; leverage is disabled")
                conn.execute("INSERT INTO positions VALUES (?, ?, ?, ?, ?, ?)",
                             (order.symbol, order.qty, price, fee, order.stop_loss, order.take_profit))
                cash -= price * order.qty + fee
            else:
                if position is None or order.qty > position["qty"] + 1e-12:
                    raise OrderRejected("Short selling is disabled")
                part = min(1.0, order.qty / position["qty"])
                realized = (price - position["avg_entry"]) * order.qty - fee - position["entry_fee"] * part
                remaining = position["qty"] - order.qty
                if remaining <= spec.qty_step / 2:
                    conn.execute("DELETE FROM positions WHERE symbol=?", (order.symbol,))
                else:
                    conn.execute("UPDATE positions SET qty=?, entry_fee=? WHERE symbol=?",
                                 (remaining, position["entry_fee"] * (1 - part), order.symbol))
                cash += price * order.qty - fee
            conn.execute("UPDATE account SET cash=? WHERE id=1", (cash,))
            conn.execute("INSERT INTO orders VALUES (?, ?, ?, ?, ?, 'filled', ?, ?, ?)",
                         (identifier, order.client_order_id, order.symbol, order.side, order.qty, order.qty, price, fee))
            conn.execute("INSERT INTO fills VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                         (identifier + "-fill", identifier, order.symbol, order.side, order.qty, price, fee,
                          self.clock().isoformat(), realized))
            row = conn.execute("SELECT * FROM orders WHERE id=?", (identifier,)).fetchone()
            return self._order(row)

    def cancel_order(self, order_id: str) -> None:
        order = self.get_order_status(order_id)
        if order.status == "filled":
            raise OrderRejected("Filled simulator orders cannot be cancelled")

    def close_position(self, symbol: str, client_order_id: str) -> BrokerOrder:
        existing = self.find_order(client_order_id)
        if existing:
            return existing
        position = next((p for p in self.get_positions() if p.symbol == symbol), None)
        if position is None:
            raise OrderRejected("No local paper position to close")
        return self.submit_order(OrderRequest(symbol, "sell", position.qty, client_order_id,
                                              self.get_quote(symbol).bid, action="CLOSE"))

    def get_order_status(self, order_id: str) -> BrokerOrder:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
        if row is None:
            raise BrokerError("Simulator order not found")
        return self._order(row)

    def find_order(self, client_order_id: str) -> BrokerOrder | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM orders WHERE client_order_id=?", (client_order_id,)).fetchone()
        return self._order(row) if row else None

    def get_fills(self, since: datetime | None = None) -> list[Fill]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM fills ORDER BY timestamp, id").fetchall()
        return [Fill(row["id"], row["order_id"], row["symbol"], row["side"], row["qty"], row["price"],
                     row["fee"], timestamp(row["timestamp"]), row["realized_pl"])
                for row in rows if since is None or timestamp(row["timestamp"]) >= since]

    def supports_protection(self, symbol: str) -> bool:
        # Emulated protection, deliberately separately identified in all UI/docs.
        return symbol in INSTRUMENTS

    def is_market_open(self, symbol: str, now: datetime) -> bool:
        if symbol not in INSTRUMENTS:
            return False
        market = INSTRUMENTS[symbol].market
        if market == "crypto":
            return True
        if market == "equity":
            import exchange_calendars as xcals
            return bool(xcals.get_calendar("XNYS").is_open_on_minute(pd.Timestamp(now).floor("min")))
        # New York close convention, with DST; broker quote.tradeable remains authoritative.
        local = pd.Timestamp(now).tz_convert("America/New_York")
        return (local.weekday() < 4 or (local.weekday() == 4 and local.hour < 17)
                or (local.weekday() == 6 and local.hour >= 17))

    def process_protection(self, symbol: str, quote: Quote) -> list[BrokerOrder]:
        self.set_quote(symbol, quote)
        with self._connect() as conn:
            row = conn.execute("SELECT p.*, (SELECT id FROM orders o WHERE o.symbol=p.symbol AND o.side='buy' "
                               "ORDER BY rowid DESC LIMIT 1) AS entry_id FROM positions p WHERE symbol=?", (symbol,)).fetchone()
        if row is None:
            return []
        stop = row["stop_loss"] is not None and quote.bid <= row["stop_loss"]
        target = row["take_profit"] is not None and quote.bid >= row["take_profit"]
        if not stop and not target:
            return []
        import hashlib
        key = "protect-" + hashlib.sha256(str(row["entry_id"]).encode()).hexdigest()[:32]
        return [self.submit_order(OrderRequest(symbol, "sell", row["qty"], key, quote.bid, action="CLOSE"))]
