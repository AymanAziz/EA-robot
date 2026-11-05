"""OANDA v20 practice adapter. Client IDs, protected longs, reduce-only exits."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import re
from urllib.parse import parse_qsl, quote as encode, urlsplit

import pandas as pd

from papertrade.domain import Account, BrokerError, BrokerOrder, Fill, INSTRUMENTS, OrderRejected
from papertrade.domain import OrderRequest, Position, Quote, SubmissionUnknown
from ._http import FixedOriginHTTP, frame, timestamp, validate_request

PRACTICE_ORIGIN = "https://api-fxpractice.oanda.com"


class OandaPractice:
    name = "oanda"

    def __init__(self, token: str, account_id: str, *, transport=None):
        if not token or not re.fullmatch(r"[0-9-]{3,40}", account_id):
            raise BrokerError("OANDA practice token or account identifier missing/invalid")
        self.account_id = account_id
        self.prefix = f"/v3/accounts/{account_id}"
        self.http = FixedOriginHTTP({PRACTICE_ORIGIN}, {"Authorization": f"Bearer {token}",
                                  "Content-Type": "application/json"}, transport)

    def _get(self, suffix, **kwargs):
        return self.http.request("GET", PRACTICE_ORIGIN, self.prefix + suffix, **kwargs)

    def _supported(self, symbol):
        if symbol not in INSTRUMENTS or INSTRUMENTS[symbol].broker != self.name:
            raise OrderRejected("Instrument unsupported by OANDA adapter")

    def get_account(self) -> Account:
        accounts = self.http.request("GET", PRACTICE_ORIGIN, "/v3/accounts")["accounts"]
        properties = next((a for a in accounts if a["id"] == self.account_id), None)
        if properties is None:
            raise BrokerError("OANDA practice account is inaccessible")
        if properties.get("mt4AccountID"):
            raise BrokerError("MT4-linked OANDA accounts cannot support required client identifiers")
        row = self._get("/summary")["account"]
        return Account(self.name, float(row["NAV"]), float(row["balance"]), row["currency"],
                       not row.get("tradingDisabled", False),
                       hashlib.sha256(("oanda:" + self.account_id).encode()).hexdigest())

    def get_positions(self) -> list[Position]:
        result = []
        for row in self._get("/openPositions")["positions"]:
            symbol = row["instrument"].replace("_", "/")
            for side in ("long", "short"):
                detail = row[side]
                qty = float(detail["units"])
                if qty:
                    q = self.get_quote(symbol)
                    result.append(Position(symbol, qty, float(detail["averagePrice"]),
                                           q.bid if qty > 0 else q.ask, self.name,
                                           float(detail.get("unrealizedPL", 0))))
        return result

    def _order(self, row: dict, fill: dict | None = None) -> BrokerOrder:
        state = row.get("state", "PENDING").lower()
        if state == "pending":
            state = "accepted"
        if fill is None and row.get("fillingTransactionID"):
            fill = self._get(f"/transactions/{encode(str(row['fillingTransactionID']), safe='')}")["transaction"]
        units = float(row.get("units", (fill or {}).get("units", 0)))
        kind = row.get("type", "").removesuffix("_ORDER")
        normalized_type = {"STOP_LOSS": "stop", "GUARANTEED_STOP_LOSS": "stop",
                           "TRAILING_STOP_LOSS": "trailing_stop", "TAKE_PROFIT": "limit"}.get(kind, kind.lower())
        stop_price = float(row["price"]) if row.get("price") and kind in {
            "STOP_LOSS", "GUARANTEED_STOP_LOSS", "STOP", "STOP_LIMIT"} else None
        limit_price = float(row["price"]) if row.get("price") and kind in {"TAKE_PROFIT", "LIMIT"} else None
        return BrokerOrder(str(row["id"]), row.get("clientExtensions", {}).get("id", ""),
                           row.get("instrument", (fill or {}).get("instrument", "")).replace("_", "/"),
                           "buy" if units > 0 else "sell", abs(units), state,
                           abs(float(fill["units"])) if fill else 0.0,
                           float(fill["price"]) if fill else None,
                           abs(float(fill.get("commission", 0))) if fill else 0.0,
                           order_type=normalized_type, stop_price=stop_price, limit_price=limit_price)

    def get_open_orders(self) -> list[BrokerOrder]:
        rows = self._get("/pendingOrders")["orders"]
        dependent = [r for r in rows if not r.get("instrument") and r.get("tradeID")]
        trades = {t["id"]: t for t in self._get("/openTrades")["trades"]} if dependent else {}
        result = []
        for original in rows:
            row = dict(original)
            if row.get("tradeID") in trades:
                trade = trades[row["tradeID"]]
                row["instrument"] = trade["instrument"]
                row["units"] = str(-float(trade["currentUnits"]))
            if not row.get("instrument"):
                raise BrokerError("Unable to identify OANDA protective order instrument")
            result.append(self._order(row))
        return result

    def get_quote(self, symbol: str) -> Quote:
        # Include externally opened positions in aggregate risk even if this bot
        # never trades their instruments. Execution remains strictly whitelisted.
        if not re.fullmatch(r"[A-Z0-9]+/[A-Z0-9]+", symbol):
            raise BrokerError("Invalid OANDA quote instrument")
        rows = self._get("/pricing", params={"instruments": symbol.replace("/", "_")})["prices"]
        if len(rows) != 1 or not rows[0].get("bids") or not rows[0].get("asks"):
            raise BrokerError("OANDA did not return an executable quote")
        row = rows[0]
        return Quote(float(row["bids"][0]["price"]), float(row["asks"][0]["price"]),
                     timestamp(row["time"]), row.get("status") == "tradeable")

    def get_market_data(self, symbol: str, start: datetime, end: datetime) -> pd.DataFrame:
        self._supported(symbol)
        rows, cursor = [], start
        for _ in range(10000):
            stop = min(cursor + timedelta(minutes=15 * 4000), end)
            if cursor >= stop:
                return frame(rows)
            result = self.http.request("GET", PRACTICE_ORIGIN,
                                       f"/v3/instruments/{symbol.replace('/', '_')}/candles",
                                       params={"granularity": "M15", "price": "M", "smooth": "false",
                                               "from": cursor.isoformat(), "to": stop.isoformat(),
                                               "includeFirst": "true"})
            for row in result["candles"]:
                opened = timestamp(row["time"])
                if row["complete"] and cursor <= opened < stop and opened + timedelta(minutes=15) <= end:
                    values = row["mid"]
                    rows.append({"timestamp": opened, "open": values["o"], "high": values["h"],
                                 "low": values["l"], "close": values["c"], "volume": row["volume"]})
            cursor = stop
        raise BrokerError("OANDA historical data page limit reached")

    def supports_protection(self, symbol: str) -> bool:
        return symbol in {"EUR/USD", "GBP/USD"}

    def is_market_open(self, symbol: str, now: datetime) -> bool:
        return self.get_quote(symbol).tradeable

    def submit_order(self, order: OrderRequest) -> BrokerOrder:
        validate_request(order)
        self._supported(order.symbol)
        existing = self.find_order(order.client_order_id)
        if existing:
            return existing
        account = self.get_account()
        if account.currency != "USD" or not account.trading_allowed:
            raise OrderRejected("OANDA requires an eligible USD practice account")
        if order.qty != int(order.qty):
            raise OrderRejected("This adapter requires whole forex units")
        specs = self._get("/instruments", params={"instruments": order.symbol.replace("/", "_")})["instruments"]
        if len(specs) != 1:
            raise OrderRejected("Instrument unavailable for this OANDA account")
        spec = specs[0]
        if order.qty < float(spec.get("minimumTradeSize", 1)):
            raise OrderRejected("Order below OANDA instrument minimum size")
        if spec.get("maximumOrderUnits") and order.qty > float(spec["maximumOrderUnits"]):
            raise OrderRejected("Order exceeds OANDA instrument maximum size")
        positions = [p for p in self.get_positions() if p.symbol == order.symbol]
        if order.side == "buy" and positions:
            raise OrderRejected("Adding to existing forex positions is disabled")
        if order.side == "buy" and order.qty * order.reference_price > min(account.cash, account.equity):
            raise OrderRejected("Forex order exceeds unleveraged account value")
        if order.side == "sell" and order.qty > sum(p.qty for p in positions):
            raise OrderRejected("Short selling is disabled")
        q = self.get_quote(order.symbol)
        if not q.tradeable:
            raise OrderRejected("Forex market is closed")
        precision = int(spec.get("displayPrecision", 5))
        payload = {"type": "MARKET", "instrument": order.symbol.replace("/", "_"),
                   "units": str(int(order.qty) * (1 if order.side == "buy" else -1)),
                   "timeInForce": "FOK", "positionFill": "OPEN_ONLY" if order.side == "buy" else "REDUCE_ONLY",
                   "clientExtensions": {"id": order.client_order_id, "tag": "papertrade"}}
        if order.side == "buy":
            payload.update({"stopLossOnFill": {"price": f"{order.stop_loss:.{precision}f}", "timeInForce": "GTC"},
                            "takeProfitOnFill": {"price": f"{order.take_profit:.{precision}f}", "timeInForce": "GTC"}})
        result = self.http.request("POST", PRACTICE_ORIGIN, self.prefix + "/orders", json={"order": payload})
        if "orderRejectTransaction" in result:
            raise OrderRejected("OANDA rejected the paper order")
        try:
            row = dict(result["orderCreateTransaction"])
            row["state"] = "FILLED" if result.get("orderFillTransaction") else (
                "CANCELLED" if result.get("orderCancelTransaction") else "PENDING")
            return self._order(row, result.get("orderFillTransaction"))
        except (KeyError, ValueError, TypeError):
            raise SubmissionUnknown("OANDA submission response invalid; reconcile by client ID") from None

    def cancel_order(self, order_id: str) -> None:
        self.http.request("PUT", PRACTICE_ORIGIN, self.prefix + f"/orders/{encode(order_id, safe='')}/cancel")

    def close_position(self, symbol: str, client_order_id: str) -> BrokerOrder:
        existing = self.find_order(client_order_id)
        if existing:
            return existing
        position = next((p for p in self.get_positions() if p.symbol == symbol and p.qty > 0), None)
        if not position:
            raise OrderRejected("No supported forex long position to close")
        return self.submit_order(OrderRequest(symbol, "sell", position.qty, client_order_id,
                                              self.get_quote(symbol).bid, action="CLOSE"))

    def get_order_status(self, order_id: str) -> BrokerOrder:
        return self._order(self._get(f"/orders/{encode(order_id, safe='')}" )["order"])

    def find_order(self, client_order_id: str) -> BrokerOrder | None:
        result = self._get(f"/orders/@{encode(client_order_id, safe='')}", allow_missing=True)
        return self._order(result["order"]) if result else None

    def get_fills(self, since: datetime | None = None) -> list[Fill]:
        # OANDA returns complete transaction pages; never silently truncate them.
        params = {"type": "ORDER_FILL", "pageSize": 1000,
                  "from": (since or datetime(2000, 1, 1, tzinfo=timezone.utc)).isoformat()}
        result = self._get("/transactions", params=params)
        fills = []
        pages = result.get("pages", [])
        if len(pages) > 1000:
            raise BrokerError("OANDA transaction page limit reached")
        for page in pages:
            parsed = urlsplit(page)
            if f"{parsed.scheme}://{parsed.netloc}" != PRACTICE_ORIGIN or parsed.path != self.prefix + "/transactions/idrange":
                raise BrokerError("Unexpected OANDA transaction pagination endpoint")
            data = self.http.request("GET", PRACTICE_ORIGIN, parsed.path, params=dict(parse_qsl(parsed.query)))
            for row in data["transactions"]:
                if row.get("type") != "ORDER_FILL":
                    continue
                units = float(row["units"])
                fills.append(Fill(str(row["id"]), str(row["orderID"]), row["instrument"].replace("_", "/"),
                                  "buy" if units > 0 else "sell", abs(units), float(row["price"]),
                                  abs(float(row.get("commission", 0))) + abs(float(row.get("guaranteedExecutionFee", 0))),
                                  timestamp(row["time"]), float(row.get("pl", 0))))
        return fills
