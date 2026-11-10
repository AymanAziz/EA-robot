"""Evaluate the frozen G1-G9 rules without optimisation."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GateEvaluation:
    verdict: str
    gates: dict[str, dict]


def evaluate_gates(inputs: dict, rules: dict) -> GateEvaluation:
    """Return all gate outcomes and the declared special-case verdict."""
    drawdown_limit = (
        float(inputs["account_usd"])
        * float(rules["g7_drawdown_account_share_max"])
    )
    checks = {
        "G1": (
            float(inputs["bootstrap_lower_bound"])
            > float(rules["g1_bootstrap_lower_gt"]),
            inputs["bootstrap_lower_bound"],
            f"> {rules['g1_bootstrap_lower_gt']}",
        ),
        "G2": (
            float(inputs["signal_minus_baseline"])
            >= float(rules["g2_edge_point_min"]),
            inputs["signal_minus_baseline"],
            f">= {rules['g2_edge_point_min']}",
        ),
        "G3": (
            float(inputs["edge_lower_bound"])
            > float(rules["g3_edge_lower_gt"]),
            inputs["edge_lower_bound"],
            f"> {rules['g3_edge_lower_gt']}",
        ),
        "G4": (
            int(inputs["positive_eras"]) >= int(rules["g4_positive_eras_min"]),
            inputs["positive_eras"],
            f">= {rules['g4_positive_eras_min']}",
        ),
        "G5": (
            int(inputs["baskets"]) >= int(rules["g5_baskets_min"]),
            inputs["baskets"],
            f">= {rules['g5_baskets_min']}",
        ),
        "G6": (
            float(inputs["gap_risk_share"])
            <= float(rules["g6_gap_risk_share_max"]),
            inputs["gap_risk_share"],
            f"<= {rules['g6_gap_risk_share_max']}",
        ),
        "G7": (
            float(inputs["mc_p99_drawdown_usd"]) <= drawdown_limit,
            inputs["mc_p99_drawdown_usd"],
            f"<= {drawdown_limit}",
        ),
        "G8": (
            float(inputs["max_fill_delta_pp"])
            <= float(rules["g8_fill_delta_pp_max"]),
            inputs["max_fill_delta_pp"],
            f"<= {rules['g8_fill_delta_pp_max']}",
        ),
        "G9": (
            bool(inputs["atr_parity"])
            is bool(rules["g9_atr_parity_required"]),
            inputs["atr_parity"],
            "passed",
        ),
    }
    gates = {
        gate: {"passed": bool(passed), "value": value, "rule": rule}
        for gate, (passed, value, rule) in checks.items()
    }
    if not gates["G9"]["passed"]:
        verdict = "PROVISIONAL_NO_VERDICT"
    elif not gates["G5"]["passed"]:
        verdict = "INSUFFICIENT_DATA"
    elif not gates["G8"]["passed"]:
        verdict = "NEEDS_M1"
    elif not gates["G7"]["passed"]:
        verdict = "NOT_TRADEABLE_AT_THIS_ACCOUNT_SIZE"
    elif all(gate["passed"] for gate in gates.values()):
        verdict = "PASS"
    else:
        verdict = "FAIL"
    return GateEvaluation(verdict=verdict, gates=gates)
