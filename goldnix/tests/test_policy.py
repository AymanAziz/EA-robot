"""Direct behaviour checks for deterministic intrabar fill policy."""

import pandas as pd
import pytest

from sim.policy import resolve_exit


@pytest.mark.parametrize(
    ("is_buy", "stop", "target", "fill_policy", "expected_price", "expected_reason"),
    [
        (True, 99.0, 102.0, "stop_first", 99.0, "stop"),
        (False, 101.4, 98.4, "target_first", 98.4, "target"),
    ],
)
def test_same_bar_policy_is_symmetric_across_quote_sides(
    is_buy, stop, target, fill_policy, expected_price, expected_reason
):
    bar = pd.Series(
        {
            "bid_open": 100.0,
            "bid_high": 103.0,
            "bid_low": 98.0,
            "ask_open": 100.4,
            "ask_high": 103.4,
            "ask_low": 98.2,
        }
    )

    decision = resolve_exit(
        bar,
        is_buy=is_buy,
        stop=stop,
        target=target,
        fill_policy=fill_policy,
        gap_policy="adverse_at_open_favourable_at_target",
        friday_flat=False,
    )

    assert decision is not None
    assert decision.price == pytest.approx(expected_price)
    assert decision.reason == expected_reason
