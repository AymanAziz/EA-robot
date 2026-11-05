"""Opt-in, read-only public feed checks. These do not verify broker credentials or orders."""
import os

import pandas as pd
import pytest

from papertrade.data import CoinbaseData, validate_candles
from papertrade.domain import utcnow

pytestmark = [pytest.mark.integration, pytest.mark.skipif(
    os.environ.get("PT_RUN_PUBLIC_DATA_INTEGRATION") != "1",
    reason="Set PT_RUN_PUBLIC_DATA_INTEGRATION=1 for real public Coinbase data")]


def test_coinbase_real_completed_candles_and_quote():
    now = utcnow()
    end = pd.Timestamp(now).floor("15min")
    start = end - pd.Timedelta(hours=3)
    adapter = CoinbaseData()
    frame = adapter.get_market_data("BTC/USD", start.to_pydatetime(), end.to_pydatetime())
    completed = validate_candles(frame, now, "crypto")
    assert len(completed) == 12
    assert (completed.high >= completed.low).all()
    assert completed.index[-1] + pd.Timedelta(minutes=15) <= now
    quote = adapter.get_quote("BTC/USD")
    assert quote.ask >= quote.bid > 0
    assert 0 <= (utcnow() - quote.timestamp).total_seconds() < 120
