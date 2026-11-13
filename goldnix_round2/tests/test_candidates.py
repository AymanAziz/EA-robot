import numpy as np
import pandas as pd
import pytest

from goldnix_round2.tests.test_execution import frame
from goldnix_round2.candidates import prepare_round2


def test_failed_breakout_waits_for_close_back_inside_prior_channel():
    bars = frame([100, 101, 102, 102, 101])
    bars.loc[3, ["bid_high", "ask_high"]] = [104., 104.2]
    bars.loc[4, ["bid_low", "ask_low"]] = [99., 99.2]
    prepared = prepare_round2(bars, {"family": "rejection", "period": 3, "stop_atr": 1})
    assert prepared.signal.tolist() == [0, 0, 0, -1, 1]


def test_both_sides_rejected_in_one_bar_is_ambiguous_and_skipped():
    bars = frame([100, 101, 102, 101])
    bars.loc[3, ["bid_high", "ask_high", "bid_low", "ask_low"]] = [104., 104.2, 98., 98.2]
    prepared = prepare_round2(bars, {"family": "rejection", "period": 3, "stop_atr": 1})
    assert prepared.signal.tolist() == [0, 0, 0, 0]


@pytest.mark.parametrize("candidate", [
    {"family": "rejection", "period": 20, "stop_atr": 1},
    {"family": "channel", "period": 20, "stop_atr": 2, "risk_share": .0025},
])
def test_new_signals_and_risk_eligibility_do_not_depend_on_future_bars(candidate):
    bars = frame(100 + np.sin(np.arange(100) / 3) * 2)
    before = prepare_round2(bars.iloc[:70], candidate)
    for name in [c for c in bars if c.startswith(("bid_", "ask_"))]:
        bars.loc[70:, name] *= 5
    after = prepare_round2(bars, candidate)
    columns = ["signal", "atr", "buy_eligible", "sell_eligible"]
    pd.testing.assert_frame_equal(before[columns], after.iloc[:70][columns])
