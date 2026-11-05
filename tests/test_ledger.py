from datetime import datetime
from types import SimpleNamespace

from papertrade.ledger import update_realized


def fill(identifier, side, qty, price, fee, symbol="SPY"):
    return SimpleNamespace(id=identifier, timestamp=datetime(2026, 1, identifier), broker="simulator",
                           symbol=symbol, side=side, qty=qty, price=price, fee=fee, realized_pl=None)


def test_fifo_profit_accounts_for_each_entry_and_exit_cost_once():
    fills = [fill(1, "buy", 10, 100, 10), fill(2, "sell", 4, 110, 2), fill(3, "sell", 6, 90, 3)]
    update_realized(fills)
    assert fills[0].realized_pl is None
    assert fills[1].realized_pl == 34
    assert fills[2].realized_pl == -69
    update_realized(fills)
    assert sum(f.realized_pl or 0 for f in fills) == -35


def test_unknown_opening_cost_basis_is_unavailable_instead_of_zero():
    fills = [fill(1, "sell", 10, 100, 1)]
    update_realized(fills)
    assert fills[0].realized_pl is None
