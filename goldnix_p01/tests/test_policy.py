import pytest

from goldnix_p01.policy import Protection, plan_protection


def test_buy_locks_half_observed_profit_after_half_risk():
    state = Protection(1, 100, 96, 112, 100, 96)
    decision = plan_protection(state, bid=102, ask=102.2, tick=0.01, stops=0.1, freeze=0, costs=0.2)
    assert decision.action == "modify"
    assert decision.stop == pytest.approx(101)
    assert decision.peak == 102


def test_sell_uses_ask_not_bid_for_activation():
    state = Protection(-1, 100, 104, 88, 100, 104)
    result = plan_protection(state, bid=98, ask=98.3, tick=0.01, stops=0.1, freeze=0, costs=0.2)
    assert result.action == "hold"


def test_retreat_keeps_peak_and_does_not_loosen_accepted_stop():
    state = Protection(1, 100, 96, 112, 106, 103)
    result = plan_protection(state, bid=104, ask=104.2, tick=0.01, stops=0.1, freeze=0, costs=0.2)
    assert result.action == "hold"
    assert result.peak == 106
    assert result.stop == 103


def test_floor_break_requests_current_price_exit():
    state = Protection(1, 100, 96, 112, 106, 103)
    result = plan_protection(state, bid=95, ask=95.2, tick=0.01, stops=0.1, freeze=0, costs=0.2)
    assert result.action == "exit"
    assert result.stop == 103


def test_stop_distance_rejection_retains_observed_peak():
    state = Protection(1, 100, 96, 112, 100, 96)
    result = plan_protection(state, bid=102, ask=102.2, tick=0.01, stops=2, freeze=0, costs=0.2)
    assert result.action == "blocked"
    assert result.peak == 102


def test_invalid_quote_fails_instead_of_creating_profit():
    with pytest.raises(ValueError):
        plan_protection(
            Protection(1, 100, 96, 112, 100, 96), bid=103, ask=102, tick=0.01, stops=0.1, freeze=0, costs=0.2
        )
