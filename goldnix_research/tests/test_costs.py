import pandas as pd
import pytest

from goldnix_research.costs import credit_spread


def test_spread_credit_uses_the_candidate_stop_multiple_and_minimum_distance():
    trades = pd.DataFrame({"atr": [2., .1], "spread_paid": [.4, .05], "r_multiple": [-1., -1.]})
    adjusted = credit_spread(trades, stop_atr=2, fraction=1)
    assert adjusted.r_multiple.tolist() == pytest.approx([-.9, -.9])
    assert trades.r_multiple.tolist() == [-1., -1.]
