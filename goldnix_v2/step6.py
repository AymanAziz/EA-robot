"""Unchanged Step-6 gate boundary for the V2 experiment."""

from __future__ import annotations

from pathlib import Path

from gates.verdict import GateEvaluation, evaluate_gates
from params.config import load_yaml


def evaluate_v2_gates(inputs: dict) -> GateEvaluation:
    """Evaluate V2 with the frozen V1 G1-G9 thresholds."""
    rules_path = Path(__file__).parents[1] / "goldnix" / "gates" / "rules.yaml"
    return evaluate_gates(inputs, load_yaml(rules_path))

