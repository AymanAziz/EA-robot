"""Read-only real paper API checks. Disabled unless explicitly opted in.

These never submit orders. Submission lifecycle tests use documented response
fixtures in tests/test_brokers.py; execute a separately monitored paper cycle to
verify actual broker fills after credentials and a validated model are available.
"""
from datetime import timedelta
import os

import pytest

from papertrade.brokers.alpaca import AlpacaPaper
from papertrade.brokers.oanda import OandaPractice
from papertrade.config import Settings
from papertrade.domain import utcnow

pytestmark = [pytest.mark.integration, pytest.mark.skipif(
    os.environ.get("PT_RUN_PAPER_INTEGRATION", "").lower() != "true",
    reason="Set PT_RUN_PAPER_INTEGRATION=true explicitly to call real paper APIs")]


def test_real_alpaca_paper_account_and_completed_crypto_data():
    settings = Settings()
    if not settings.alpaca_key.get_secret_value() or not settings.alpaca_secret.get_secret_value():
        pytest.skip("Alpaca paper credentials missing")
    broker = AlpacaPaper(settings.alpaca_key.get_secret_value(), settings.alpaca_secret.get_secret_value())
    account = broker.get_account()
    assert account.currency == "USD" and account.equity > 0
    end = utcnow()
    data = broker.get_market_data("BTC/USD", end - timedelta(days=1), end)
    assert not data.empty
    assert data.index.max().to_pydatetime() + timedelta(minutes=15) <= end
    assert broker.get_quote("BTC/USD").bid > 0
    broker.get_open_orders()
    broker.get_positions()


def test_real_oanda_practice_account_and_completed_forex_data():
    settings = Settings()
    if not settings.oanda_token.get_secret_value() or not settings.oanda_account_id.get_secret_value():
        pytest.skip("OANDA practice credentials missing")
    broker = OandaPractice(settings.oanda_token.get_secret_value(), settings.oanda_account_id.get_secret_value())
    account = broker.get_account()
    assert account.currency == "USD" and account.equity > 0
    end = utcnow()
    data = broker.get_market_data("EUR/USD", end - timedelta(days=7), end)
    assert not data.empty
    assert data.index.max().to_pydatetime() + timedelta(minutes=15) <= end
    broker.get_open_orders()
    broker.get_positions()
