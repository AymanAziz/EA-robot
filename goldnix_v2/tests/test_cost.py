"""Behaviour tests for the V2 signal-bar transaction-cost gate."""

import numpy as np

from goldnix_v2.cost import cost_eligible


def test_cost_gate_accepts_exact_budget_and_rejects_higher_or_invalid_cost():
    close_spread = np.array([0.15, 0.1501, np.nan, 0.10])
    atr = np.array([1.0, 1.0, 1.0, 0.0])

    eligible = cost_eligible(close_spread, atr, max_spread_atr=0.15)

    assert eligible.tolist() == [True, False, False, False]

