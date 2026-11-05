from dataclasses import replace

import pandas as pd
import pytest

from papertrade.domain import Account, BrokerError, utcnow
from papertrade.data import DataError
from papertrade.engine import TradingEngine


def test_historical_provider_cannot_change_inside_a_symbol_dataset(db):
    data = pd.DataFrame({"open": [100], "high": [102], "low": [99], "close": [101], "volume": [10]},
                         index=pd.DatetimeIndex(["2026-11-01T00:00:00Z"]))
    db.store_candles("BTC/USD", data, "CoinbaseData")
    with pytest.raises(DataError, match="provider changed"):
        db.store_candles("BTC/USD", data, "AlpacaPaper")
    assert len(db.load_candles("BTC/USD")) == 1


def test_paper_venues_cannot_share_one_portfolio_history(settings, db):
    TradingEngine(settings, db, brokers={}, sources={})
    with pytest.raises(BrokerError, match="venue changed"):
        TradingEngine(settings.model_copy(update={"execution": "brokers"}), db, brokers={}, sources={})


def test_changing_paper_account_fails_reconciliation_without_invented_returns(settings, db):
    class IdentityBroker:
        name = "simulator"
        account = Account("simulator", 10000, 10000, identity="first-paper-account-hash")
        def get_account(self):
            return self.account
        def get_positions(self):
            return []
        def get_open_orders(self):
            return []
        def get_fills(self, since=None):
            return []
    broker = IdentityBroker()
    engine = TradingEngine(settings, db, brokers={"simulator": broker}, sources={})
    assert engine.reconcile(utcnow())
    broker.account = replace(broker.account, equity=100000, cash=100000, identity="different-account-hash")
    assert not engine.reconcile(utcnow())
    assert not engine.portfolio.reconciled
