"""Behaviour tests for G1-G9 evaluation and special verdict precedence."""

from pathlib import Path

import pytest

from gates.verdict import evaluate_gates
from params.config import load_yaml

RULES = Path(__file__).parents[1] / "gates" / "rules.yaml"


def _passing_inputs(**overrides):
    values = {
        "bootstrap_lower_bound": 0.01,
        "signal_minus_baseline": 0.10,
        "edge_lower_bound": 0.01,
        "positive_eras": 3,
        "baskets": 1000,
        "gap_risk_share": 0.10,
        "mc_p99_drawdown_usd": 12.0,
        "account_usd": 100.0,
        "max_fill_delta_pp": 8.0,
        "atr_parity": True,
    }
    values.update(overrides)
    return values


def test_all_boundary_compliant_inputs_pass():
    result = evaluate_gates(_passing_inputs(), load_yaml(RULES))

    assert result.verdict == "PASS"
    assert all(gate["passed"] for gate in result.gates.values())


@pytest.mark.parametrize(
    ("override", "verdict"),
    [
        ({"atr_parity": False}, "PROVISIONAL_NO_VERDICT"),
        ({"baskets": 999}, "INSUFFICIENT_DATA"),
        ({"max_fill_delta_pp": 8.01}, "NEEDS_M1"),
        ({"mc_p99_drawdown_usd": 12.01}, "NOT_TRADEABLE_AT_THIS_ACCOUNT_SIZE"),
        ({"bootstrap_lower_bound": 0.0}, "FAIL"),
    ],
)
def test_failed_gate_maps_to_declared_verdict(override, verdict):
    result = evaluate_gates(_passing_inputs(**override), load_yaml(RULES))

    assert result.verdict == verdict
