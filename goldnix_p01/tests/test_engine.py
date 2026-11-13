import pytest

from goldnix_p01.engine import Broker, Contract


def test_gap_executes_existing_stop_before_a_timer_can_save_profit():
    broker = Broker(Contract())
    broker.open(side=1, utc=1000, bid=100, ask=100.2, distance=2, atr=1)
    broker.quote(1001_000, bid=101.4, ask=101.6)
    broker.protect(1001, bid=101.4, ask=101.6)
    broker.quote(1002_000, bid=99, ask=99.2)
    assert broker.position is None
    assert broker.trades[0]["exit_reason"] == "sl"
    assert broker.trades[0]["exit"] == 99
    assert broker.trades[0]["pnl_usc"] == pytest.approx(-1.2)


def test_strategy_waits_for_completed_breakout_and_uses_same_quote_for_sell():
    import numpy as np
    from goldnix_p01.data import TICK_DTYPE
    from goldnix_p01.replay import TIMER_DTYPE, replay

    start = 1706749200  # 2024-02-01 01:00 UTC, Thursday.
    rows = []
    for minute in range(104):
        price = 100 if minute < 100 else 99 if minute < 102 else 101
        rows.extend(
            [
                (1000 * (start + 60 * minute), price, price + 0.1),
                (1000 * (start + 60 * minute + 20), price + 0.2, price + 0.3),
                (1000 * (start + 60 * minute + 40), price - 0.2, price - 0.1),
            ]
        )
    ticks = np.array(rows, dtype=TICK_DTYPE)
    timers = np.zeros(104 * 60 - 1, dtype=TIMER_DTYPE)
    timers["utc"] = np.arange(start + 1, start + 104 * 60)
    indices = np.searchsorted(ticks["utc_ms"], timers["utc"] * 1000, side="right") - 1
    timers["quote_ms"] = ticks["utc_ms"][indices]
    timers["bid"] = ticks["bid"][indices]
    timers["ask"] = ticks["ask"][indices]
    timers["end"] = start + 86400
    result = replay(ticks, timers, Contract(), offset=0)
    assert len(result["trades"]) == 1
    assert result["trades"][0]["side"] == -1
    assert result["trades"][0]["entry_utc"] == start + 101 * 60
    assert result["trades"][0]["entry"] == 99
    assert result["trades"][0]["exit_reason"] == "sl"


def test_decimal_sell_stop_triggers_on_its_exact_broker_price():
    broker = Broker(Contract())
    broker.open(side=-1, utc=1000, bid=2056.03, ask=2056.23, distance=1.901428571429, atr=0.950714285714)
    broker.protect(1001, bid=2054.70, ask=2054.91)
    assert broker.position["protection"].accepted_stop == pytest.approx(2055.47)
    broker.quote(1002_000, bid=2055.26, ask=2055.47)
    assert broker.position is None
    assert broker.trades[0]["exit"] == 2055.47


def test_favourable_target_gap_policy_is_explicit_not_fitted_to_a_result():
    for policy, fill in [("level", 106), ("quote", 107)]:
        broker = Broker(Contract(target_fill=policy))
        broker.open(side=1, utc=1000, bid=100, ask=100.2, distance=2, atr=1)
        broker.quote(1001_000, bid=107, ask=107.2)
        assert broker.trades[0]["exit"] == fill
        assert broker.trades[0]["exit_reason"] == "tp"


@pytest.mark.parametrize(
    "options",
    [{"leverage": 0}, {"tick": float("nan")}, {"round_trip_cost": -1}, {"target_fill": "best_possible"}],
)
def test_invalid_execution_assumptions_are_rejected(options):
    with pytest.raises(ValueError):
        Contract(**options)


def test_timer_cannot_see_a_quote_from_a_later_second():
    import numpy as np
    from goldnix_p01.data import TICK_DTYPE
    from goldnix_p01.replay import TIMER_DTYPE, replay

    ticks = np.array([(1000, 100, 100.2), (2000, 101, 101.2)], dtype=TICK_DTYPE)
    timers = np.array([(1, 2000, 101, 101.2, 86400, 0)], dtype=TIMER_DTYPE)
    with pytest.raises(ValueError, match="future"):
        replay(ticks, timers, Contract(), offset=0)
