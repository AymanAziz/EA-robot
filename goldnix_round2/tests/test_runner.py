from goldnix_round2.tests.test_execution import config, frame
from goldnix_round2.runner import evaluate_candidate


def test_screen_never_promotes_tiny_sample_or_product_scenario_to_approval():
    bars = frame([100, 101, 102, 104, 99, 98, 100] * 20)
    candidate = {"id": "TEST", "family": "channel", "period": 3,
                 "stop_atr": 1, "reward_ratio": 2, "exit_management": "break_even"}
    protocol = {"trial_count": 52, "bootstrap_resamples": 100, "bootstrap_seed": 7,
                "monte_carlo_paths": 1000, "monte_carlo_seed": 8}
    result, trades = evaluate_candidate({"A": bars}, candidate, config(), protocol)
    assert result["baskets"] > 0
    assert result["G5"] is False
    assert result["selected_for_full_evaluation"] is False
    assert result["approval"] is False
    assert result["account_verified"] is False
    assert result["unevaluated_gates"] == ["G2", "G3"]
    assert trades.r_multiple.notna().all()
