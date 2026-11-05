"""Small HTTP transport with fixed origins and deliberately no mutation retries."""
from __future__ import annotations

from datetime import datetime, timezone
import math
import re

import httpx
import pandas as pd

from papertrade.domain import BrokerError, OrderRejected, SubmissionUnknown


def timestamp(value: str | datetime) -> datetime:
    return pd.Timestamp(value).to_pydatetime().astimezone(timezone.utc)


def validate_request(order):
    if not order.client_order_id or not re.fullmatch(r"[A-Za-z0-9_-]{1,48}", order.client_order_id):
        raise OrderRejected("Invalid idempotency identifier")
    if order.side not in {"buy", "sell"} or not math.isfinite(order.qty) or order.qty <= 0:
        raise OrderRejected("Quantity must be finite and positive")
    if not math.isfinite(order.reference_price) or order.reference_price <= 0:
        raise OrderRejected("A positive reference price is required")
    if order.side == "buy":
        if order.stop_loss is None or order.take_profit is None:
            raise OrderRejected("New positions require protective stop and target prices")
        if not (0 < order.stop_loss < order.reference_price < order.take_profit < float("inf")):
            raise OrderRejected("Invalid long position protection prices")


def frame(rows: list[dict]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"],
                            index=pd.DatetimeIndex([], tz="UTC", name="timestamp"))
    result = pd.DataFrame(rows)
    result["timestamp"] = pd.to_datetime(result["timestamp"], utc=True)
    return result.set_index("timestamp").sort_index().astype(float)


class FixedOriginHTTP:
    def __init__(self, origins: set[str], headers: dict[str, str], transport=None):
        self.origins = frozenset(origins)
        self.client = httpx.Client(headers=headers, timeout=httpx.Timeout(20, connect=10),
                                   follow_redirects=False, transport=transport, trust_env=False)

    def request(self, method: str, origin: str, path: str, *, allow_missing=False, **kwargs):
        if origin not in self.origins or not path.startswith("/") or path.startswith("//"):
            raise BrokerError("Forbidden broker endpoint")
        mutation = method.upper() not in {"GET", "HEAD"}
        try:
            response = self.client.request(method, origin + path, follow_redirects=False, **kwargs)
        except (httpx.HTTPError, OSError):
            if mutation:
                raise SubmissionUnknown("Paper broker request outcome unknown; reconcile by client ID") from None
            raise BrokerError("Paper broker unavailable") from None
        if response.status_code == 404 and allow_missing:
            return None
        if 300 <= response.status_code < 400:
            raise BrokerError("Broker redirect blocked")
        if not response.is_success:
            if mutation and (response.status_code >= 500 or response.status_code == 408):
                raise SubmissionUnknown("Paper broker outcome unknown; reconcile by client ID")
            if mutation and response.status_code in {400, 403, 409, 422, 429}:
                raise OrderRejected(f"Paper broker rejected request (HTTP {response.status_code})")
            raise BrokerError(f"Paper broker request failed (HTTP {response.status_code})")
        if response.status_code == 204:
            return {}
        try:
            return response.json()
        except (ValueError, TypeError):
            if mutation:
                raise SubmissionUnknown("Invalid broker response after submission; reconciliation required") from None
            raise BrokerError("Invalid paper broker response") from None

    def close(self):
        self.client.close()
