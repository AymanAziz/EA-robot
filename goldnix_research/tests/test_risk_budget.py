import pandas as pd

from goldnix_research.risk_budget import apply_risk_budget


def test_risk_budget_includes_spread_and_removes_ineligible_baseline_opportunities():
    frame = pd.DataFrame({"atr": [4., 5., float("nan")], "bid_close": [100.] * 3,
                          "ask_close": [100.4] * 3, "signal": [1, 1, -1],
                          "buy_eligible": [True] * 3, "sell_eligible": [True] * 3})
    filtered = apply_risk_budget(frame, stop_atr=2, account_usd=20,
                                 risk_share=.005, usd_per_price_unit=.01)
    assert filtered.signal.tolist() == [1, 0, 0]
    assert filtered.buy_eligible.tolist() == [True, False, False]
    assert filtered.sell_eligible.tolist() == [True, False, False]
    assert frame.signal.tolist() == [1, 1, -1]
