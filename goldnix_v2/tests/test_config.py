"""Contract test for the frozen-before-results V2 decision config."""

from pathlib import Path

from params.config import load_yaml


def test_v2_decision_config_contains_the_predeclared_single_candidate():
    config = load_yaml(Path(__file__).parents[1] / "decision.yaml")

    assert config["strategy_version"] == 2
    assert config["server_timezone"] == "Europe/Helsinki"
    assert config["account_usd"] == 20.0
    assert config["aroon_period"] == 70
    assert config["h4_aroon_period"] == 70
    assert config["h4_trend_rule"] == "oscillator_sign"
    assert config["vol_ceiling_atr"] == 0.15
    assert config["max_layers"] == 1
    assert config["fill_policy"] == "stop_first"
    assert config["baseline_draws"] == 200
    assert config["bootstrap_resamples"] == 10_000
    assert config["monte_carlo_paths"] == 100_000

