"""Alpaca paper trading only. All execution origins are immutable."""
from __future__ import annotations

from datetime import datetime, timedelta
import hashlib
import math
from urllib.parse import quote as encode

import pandas as pd

from papertrade.domain import Account, BrokerError, BrokerOrder, Fill, INSTRUMENTS, OrderRejected
from papertrade.domain import OrderRequest, Position, Quote, SubmissionUnknown, utcnow
from ._http import FixedOriginHTTP, frame, timestamp, validate_request

PAPER_ORIGIN = "https://paper-api.alpaca.markets"
DATA_ORIGIN = "https://data.alpaca.markets"


def _symbol(value: str) -> str:
    return {"BTCUSD": "BTC/USD", "ETHUSD": "ETH/USD"}.get(value, value)


def _order(row) -> BrokerOrder:
    return BrokerOrder(str(row["id"]), row.get("client_order_id", ""), _symbol(row["symbol"]),
                       row["side"], float(row.get("qty") or 0), row["status"],
                       float(row.get("filled_qty") or 0),
                       float(row["filled_avg_price"]) if row.get("filled_avg_price") else None,
                       order_type=row.get("type", ""),
                       stop_price=float(row["stop_price"]) if row.get("stop_price") else None,
                       limit_price=float(row["limit_price"]) if row.get("limit_price") else None)


class AlpacaPaper:
    name = "alpaca"

    def __init__(self, key: str, secret: str, *, transport=None):
        if not key or not secret:
            raise BrokerError("Alpaca paper credentials missing")
        self.http = FixedOriginHTTP({PAPER_ORIGIN, DATA_ORIGIN},
                                   {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret}, transport)

    def _get(self, path, **kwargs):
        return self.http.request("GET", PAPER_ORIGIN, path, **kwargs)

    def _supported(self, symbol):
        if symbol not in INSTRUMENTS or INSTRUMENTS[symbol].broker != self.name:
            raise OrderRejected("Instrument unsupported by Alpaca adapter")

    def get_account(self) -> Account:
        row = self._get("/v2/account")
        allowed = (row.get("status") in {"ACTIVE", "PAPER_ONLY"} and not row.get("trading_blocked", True)
                   and not row.get("account_blocked", True))
        identity = hashlib.sha256(("alpaca:" + str(row["id"])).encode()).hexdigest() if row.get("id") else ""
        return Account(self.name, float(row["equity"]), float(row["cash"]), row["currency"], allowed, identity)

    def get_positions(self) -> list[Position]:
        return [Position(_symbol(p["symbol"]), float(p["qty"]), float(p["avg_entry_price"]),
                         float(p["current_price"]), self.name, float(p.get("unrealized_pl", 0)))
                for p in self._get("/v2/positions")]

    def get_open_orders(self) -> list[BrokerOrder]:
        rows = self._get("/v2/orders", params={"status": "open", "limit": 500, "nested": "true"})
        if len(rows) >= 500:
            raise BrokerError("Too many open Alpaca orders to reconcile safely")
        result = {}
        def collect(row):
            item = _order(row)
            if item.status not in {"filled", "canceled", "cancelled", "expired", "rejected", "replaced"}:
                result[item.id] = item
            for leg in row.get("legs") or []:
                collect(leg)
        for row in rows:
            collect(row)
        return list(result.values())

    def get_quote(self, symbol: str) -> Quote:
        self._supported(symbol)
        if INSTRUMENTS[symbol].market == "crypto":
            data = self.http.request("GET", DATA_ORIGIN, "/v1beta3/crypto/us/latest/quotes",
                                     params={"symbols": symbol})
            row = data["quotes"][symbol]
        else:
            data = self.http.request("GET", DATA_ORIGIN, f"/v2/stocks/{encode(symbol, safe='')}/quotes/latest",
                                     params={"feed": "iex"})
            row = data["quote"]
        return Quote(float(row["bp"]), float(row["ap"]), timestamp(row["t"]))

    def get_market_data(self, symbol: str, start: datetime, end: datetime) -> pd.DataFrame:
        self._supported(symbol)
        crypto = INSTRUMENTS[symbol].market == "crypto"
        path = "/v1beta3/crypto/us/bars" if crypto else "/v2/stocks/bars"
        params = {"symbols": symbol, "timeframe": "15Min", "start": start.isoformat(),
                  "end": end.isoformat(), "limit": 10000, "sort": "asc"}
        if not crypto:
            params.update({"feed": "iex", "adjustment": "raw"})
        rows, seen = [], set()
        for _ in range(1000):
            data = self.http.request("GET", DATA_ORIGIN, path, params=params)
            for bar in data.get("bars", {}).get(symbol, []):
                opened = timestamp(bar["t"])
                if start <= opened < end and opened + timedelta(minutes=15) <= min(end, utcnow()):
                    rows.append({"timestamp": opened, "open": bar["o"], "high": bar["h"],
                                 "low": bar["l"], "close": bar["c"], "volume": bar["v"]})
            token = data.get("next_page_token")
            if not token:
                return frame(rows)
            if token in seen:
                raise BrokerError("Alpaca pagination did not advance")
            seen.add(token)
            params["page_token"] = token
        raise BrokerError("Alpaca historical data page limit reached")

    def supports_protection(self, symbol: str) -> bool:
        return symbol in {"SPY", "QQQ"}

    def is_market_open(self, symbol: str, now: datetime) -> bool:
        self._supported(symbol)
        if INSTRUMENTS[symbol].market == "crypto":
            return True
        return bool(self._get("/v2/clock")["is_open"])

    def submit_order(self, order: OrderRequest) -> BrokerOrder:
        validate_request(order)
        self._supported(order.symbol)
        existing = self.find_order(order.client_order_id)
        if existing:
            return existing
        account = self.get_account()
        if account.currency != "USD" or not account.trading_allowed:
            raise OrderRejected("Alpaca paper account is not eligible for trading")
        asset = self._get(f"/v2/assets/{encode(order.symbol.replace('/', ''), safe='')}")
        if not asset.get("tradable") or asset.get("status") != "active":
            raise OrderRejected("Instrument is not currently tradable")
        if asset.get("min_order_size") and order.qty < float(asset["min_order_size"]):
            raise OrderRejected("Order below Alpaca instrument minimum size")
        if asset.get("min_trade_increment"):
            step = float(asset["min_trade_increment"])
            if step <= 0 or not math.isclose(order.qty / step, round(order.qty / step), rel_tol=1e-10, abs_tol=1e-7):
                raise OrderRejected("Order violates Alpaca instrument quantity increment")
        positions = self.get_positions()
        position = next((p for p in positions if p.symbol == order.symbol), None)
        if order.side == "buy" and position and abs(position.qty) > 0:
            raise OrderRejected("Adding to existing positions is disabled")
        if order.side == "buy" and order.qty * order.reference_price > account.cash:
            raise OrderRejected("Insufficient paper cash; margin borrowing is disabled")
        if order.side == "sell" and (position is None or position.qty < order.qty):
            raise OrderRejected("Short selling is disabled")
        if not self.is_market_open(order.symbol, utcnow()):
            raise OrderRejected("Market is closed")
        crypto = INSTRUMENTS[order.symbol].market == "crypto"
        payload = {"symbol": order.symbol, "qty": str(order.qty), "side": order.side,
                   "type": "market", "time_in_force": "gtc" if crypto else "day",
                   "client_order_id": order.client_order_id}
        if order.side == "buy" and not crypto:
            if order.qty != int(order.qty):
                raise OrderRejected("Equity bracket orders require whole shares")
            payload.update({"order_class": "bracket", "stop_loss": {"stop_price": f"{order.stop_loss:.2f}"},
                            "take_profit": {"limit_price": f"{order.take_profit:.2f}"}})
        if order.side == "sell":
            # Cancel protections before submitting a close. Cancellation can be asynchronous.
            for pending in self.get_open_orders():
                if pending.symbol == order.symbol:
                    self.cancel_order(pending.id)
            if any(p.symbol == order.symbol for p in self.get_open_orders()):
                raise OrderRejected("Position has pending orders; wait for cancellation confirmation")
        try:
            row = self.http.request("POST", PAPER_ORIGIN, "/v2/orders", json=payload)
            return _order(row)
        except (KeyError, ValueError, TypeError):
            raise SubmissionUnknown("Alpaca submission response invalid; reconcile by client ID") from None

    def cancel_order(self, order_id: str) -> None:
        self.http.request("DELETE", PAPER_ORIGIN, f"/v2/orders/{encode(order_id, safe='')}")

    def close_position(self, symbol: str, client_order_id: str) -> BrokerOrder:
        existing = self.find_order(client_order_id)
        if existing:
            return existing
        position = next((p for p in self.get_positions() if p.symbol == symbol and p.qty > 0), None)
        if not position:
            raise OrderRejected("No supported long position to close")
        return self.submit_order(OrderRequest(symbol, "sell", position.qty, client_order_id,
                                              self.get_quote(symbol).bid, action="CLOSE"))

    def get_order_status(self, order_id: str) -> BrokerOrder:
        return _order(self._get(f"/v2/orders/{encode(order_id, safe='')}"))

    def find_order(self, client_order_id: str) -> BrokerOrder | None:
        row = self._get("/v2/orders:by_client_order_id", params={"client_order_id": client_order_id},
                        allow_missing=True)
        return _order(row) if row else None

    def get_fills(self, since: datetime | None = None) -> list[Fill]:
        params = {"activity_types": "FILL", "direction": "asc", "page_size": 100}
        if since:
            params["after"] = since.isoformat()
        result, seen = [], set()
        for _ in range(1000):
            rows = self._get("/v2/account/activities/FILL", params=params)
            for row in rows:
                result.append(Fill(str(row["id"]), str(row["order_id"]), _symbol(row["symbol"]),
                                   row["side"], float(row["qty"]), float(row["price"]),
                                   float(row.get("commission", 0)), timestamp(row["transaction_time"]),
                                   fees_final="commission" in row))
            if len(rows) < 100:
                return result
            token = rows[-1]["id"]
            if token in seen:
                raise BrokerError("Alpaca fill pagination did not advance")
            seen.add(token)
            params["page_token"] = token
        raise BrokerError("Alpaca fill page limit reached")
