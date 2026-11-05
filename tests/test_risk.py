from datetime import datetime, timedelta, timezone

import pytest

from papertrade.domain import INSTRUMENTS, Position, Quote
from papertrade.risk import Portfolio, RiskContext, approve_entry


NOW = datetime(2026, 11, 5, 14, 0, 20, tzinfo=timezone.utc)


def context(**kwargs):
    values = dict(now=NOW, candle_at=NOW.replace(minute=45, hour=13, second=0),
                  quote=Quote(99.99, 100.01, NOW), market_open=True, model_valid=True,
                  protected=True, volume=100000, atr=1)
    values.update(kwargs)
    return RiskContext(**values)


def portfolio(**kwargs):
    return Portfolio(**(dict(equity=10000, cash=10000, daily_start_equity=10000,
                             peak_equity=10000, positions=[], reserved_exposure=0,
                             reserved_positions=0, reconciled=True) | kwargs))


def test_position_size_respects_both_stop_risk_and_notional_cap(settings):
    decision = approve_entry(INSTRUMENTS["SPY"], portfolio(), context(), settings)
    assert decision.approved
    assert decision.qty == 19  # USD 2,000 cap divided by ask plus costs, whole shares
    assert decision.stop_loss < 100 < decision.take_profit


@pytest.mark.parametrize("changes,reason", [
    ({"equity": 9799}, "daily_loss"),
    ({"equity": 8999, "daily_start_equity": 8999}, "drawdown"),
    ({"reconciled": False}, "reconciliation"),
    ({"cash": 0}, "cash"),
    ({"reserved_positions": 3}, "position_limit"),
])
def test_global_limits_block_new_risk(settings, changes, reason):
    result = approve_entry(INSTRUMENTS["SPY"], portfolio(**changes), context(), settings)
    assert not result.approved
    assert reason in result.reason


@pytest.mark.parametrize("changes,reason", [
    ({"killed": True}, "kill"), ({"paused": True}, "paused"),
    ({"market_open": False}, "market_closed"),
    ({"session_remaining_ok": False}, "session_closes_before_horizon"),
    ({"model_valid": False}, "model"), ({"protected": False}, "protection"),
    ({"quote": Quote(90, 110, NOW)}, "spread"),
    ({"quote": Quote(99, 100, NOW - timedelta(minutes=5))}, "stale_quote"),
    ({"candle_at": NOW - timedelta(hours=2)}, "stale_data"),
    ({"candle_at": NOW}, "incomplete"), ({"atr": float("nan")}, "invalid"),
    ({"volume": 0}, "liquidity"),
])
def test_independent_risk_guards(settings, changes, reason):
    result = approve_entry(INSTRUMENTS["SPY"], portfolio(), context(**changes), settings)
    assert not result.approved
    assert reason in result.reason


def test_correlated_markets_share_one_budget(settings):
    held = Position("QQQ", 9, 200, 200, "alpaca")
    result = approve_entry(INSTRUMENTS["SPY"], portfolio(positions=[held]), context(), settings)
    assert result.approved
    assert result.qty <= 11  # shared USD3,000 correlation cap, 1,800 already used


def test_averaging_and_unsupported_positions_block_entries(settings):
    held = Position("SPY", 1, 110, 100, "alpaca")
    assert not approve_entry(INSTRUMENTS["SPY"], portfolio(positions=[held]), context(), settings).approved
    unknown = Position("UNKNOWN", 1, 100, 100, "alpaca")
    assert not approve_entry(INSTRUMENTS["SPY"], portfolio(positions=[unknown]), context(), settings).approved
