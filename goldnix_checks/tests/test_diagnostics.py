import pandas as pd
import pytest

from goldnix_checks.diagnostics import rebated_trades


def test_cost_diagnostic_rebates_money_using_stop_floor_and_keeps_trade_count():
    trades = pd.DataFrame({"atr": [1.0, 0.2], "spread_paid": [0.2, 0.1],
                           "r_multiple": [0.8, -1.2]})
    result = rebated_trades(trades, fraction=0.5)

    assert result.r_multiple.tolist() == pytest.approx([0.9, -1.1])
    assert trades.r_multiple.tolist() == [0.8, -1.2]
    assert len(result) == 2
