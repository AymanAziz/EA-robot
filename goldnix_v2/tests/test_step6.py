"""Behaviour test for the unchanged V2 Step-6 gate boundary."""

from goldnix_v2.step6 import evaluate_v2_gates


def test_step6_reports_every_unchanged_gate_without_forcing_a_pass():
    inputs = {
        "account_usd": 20.0,
        "bootstrap_lower_bound": 0.01,
        "signal_minus_baseline": 0.11,
        "edge_lower_bound": 0.01,
        "positive_eras": 3,
        "baskets": 1000,
        "gap_risk_share": 0.01,
        "mc_p99_drawdown_usd": 3.0,
        "max_fill_delta_pp": 1.0,
        "atr_parity": True,
    }

    result = evaluate_v2_gates(inputs)

    assert list(result.gates) == [f"G{number}" for number in range(1, 10)]
    assert result.gates["G7"]["passed"] is False
    assert result.verdict == "NOT_TRADEABLE_AT_THIS_ACCOUNT_SIZE"

