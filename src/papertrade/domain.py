"""Public, provider-independent contracts. All timestamps are timezone-aware UTC."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal, Protocol

import pandas as pd


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class Instrument:
    symbol: str
    market: Literal["crypto", "equity", "forex"]
    broker: str
    correlation_group: str
    fee_bps: float
    slippage_bps: float
    max_spread_bps: float
    qty_step: float
    min_qty: float
    max_exposure: float = 0.20
    min_volume: float = 1.0
    stop_atr: float = 2.0
    reward_risk: float = 2.0


INSTRUMENTS = {
    "BTC/USD": Instrument("BTC/USD", "crypto", "alpaca", "crypto", 25, 10, 40, 0.000001, 0.00001),
    "ETH/USD": Instrument("ETH/USD", "crypto", "alpaca", "crypto", 25, 10, 40, 0.00001, 0.0001),
    "SPY": Instrument("SPY", "equity", "alpaca", "us_index", 1, 2, 15, 1, 1),
    "QQQ": Instrument("QQQ", "equity", "alpaca", "us_index", 1, 2, 15, 1, 1),
    "EUR/USD": Instrument("EUR/USD", "forex", "oanda", "usd_fx", 0, 1, 8, 1, 1),
    "GBP/USD": Instrument("GBP/USD", "forex", "oanda", "usd_fx", 0, 1, 8, 1, 1),
}


@dataclass(frozen=True)
class Account:
    broker: str
    equity: float
    cash: float
    currency: str = "USD"
    trading_allowed: bool = True
    identity: str = ""


@dataclass(frozen=True)
class Position:
    symbol: str
    qty: float
    avg_entry: float
    current_price: float
    broker: str
    unrealized_pl: float = 0.0
    stop_loss: float | None = None
    take_profit: float | None = None


@dataclass(frozen=True)
class Quote:
    bid: float
    ask: float
    timestamp: datetime
    tradeable: bool = True

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2

    @property
    def spread_bps(self) -> float:
        return (self.ask - self.bid) / self.mid * 10000 if self.mid > 0 else float("inf")


@dataclass(frozen=True)
class OrderRequest:
    symbol: str
    side: Literal["buy", "sell"]
    qty: float
    client_order_id: str
    reference_price: float
    stop_loss: float | None = None
    take_profit: float | None = None
    action: str = "BUY"


@dataclass(frozen=True)
class BrokerOrder:
    id: str
    client_order_id: str
    symbol: str
    side: str
    qty: float
    status: str
    filled_qty: float = 0.0
    filled_avg_price: float | None = None
    fees: float = 0.0
    order_type: str = ""
    stop_price: float | None = None
    limit_price: float | None = None


@dataclass(frozen=True)
class Fill:
    id: str
    order_id: str
    symbol: str
    side: str
    qty: float
    price: float
    fee: float
    timestamp: datetime
    realized_pl: float = 0.0
    fees_final: bool = True


class BrokerError(RuntimeError):
    """Safe public error; never include raw responses or credentials."""


class OrderRejected(BrokerError):
    pass


class SubmissionUnknown(BrokerError):
    """A request may have reached the provider. Query; never blindly resubmit."""


class Broker(Protocol):
    name: str
    def get_account(self) -> Account: ...
    def get_positions(self) -> list[Position]: ...
    def get_open_orders(self) -> list[BrokerOrder]: ...
    def get_quote(self, symbol: str) -> Quote: ...
    def get_market_data(self, symbol: str, start: datetime, end: datetime) -> pd.DataFrame: ...
    def submit_order(self, order: OrderRequest) -> BrokerOrder: ...
    def cancel_order(self, order_id: str) -> None: ...
    def close_position(self, symbol: str, client_order_id: str) -> BrokerOrder: ...
    def get_order_status(self, order_id: str) -> BrokerOrder: ...
    def find_order(self, client_order_id: str) -> BrokerOrder | None: ...
    def get_fills(self, since: datetime | None = None) -> list[Fill]: ...
    def supports_protection(self, symbol: str) -> bool: ...
    def is_market_open(self, symbol: str, now: datetime) -> bool: ...
