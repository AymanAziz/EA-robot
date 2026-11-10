"""Behaviour tests for strict YAML configuration loading."""

from pathlib import Path

import pytest

from params.config import dump_yaml, load_yaml

DECISION_CONFIG = Path(__file__).parents[1] / "params" / "decision.yaml"
EXPECTED_DECISION = {
    "aroon_period": 70,
    "threshold": 50,
    "ties": "newest",
    "volume_filter": "none",
    "vol_ceiling_atr": 0.30,
    "news_filter": False,
    "stop_atr": 1.0,
    "target_atr": 2.0,
    "min_distance_usd": 0.50,
    "max_layers": 1,
    "trailing": False,
    "one_position": True,
    "session_filter": "none",
    "friday_no_entry_from_utc": "19:00",
    "friday_flat_utc": "20:00",
    "daily_halt_r": -2.0,
    "holiday_exclusion": True,
    "fill_policy": "stop_first",
    "gap_policy": "adverse_at_open_favourable_at_target",
}


@pytest.mark.parametrize("bare_boolean", ["on", "off", "yes", "no"])
def test_strict_yaml_rejects_ambiguous_bare_boolean_words(tmp_path, bare_boolean):
    config = tmp_path / "ambiguous.yaml"
    config.write_text(f"setting: {bare_boolean}\n", encoding="utf-8")

    with pytest.raises(ValueError, match="ambiguous YAML boolean"):
        load_yaml(config)


def test_decision_config_round_trips_to_expected_python_values(tmp_path):
    loaded = load_yaml(DECISION_CONFIG)
    emitted = tmp_path / "decision.yaml"

    dump_yaml(loaded, emitted)

    assert loaded == EXPECTED_DECISION
    assert load_yaml(emitted) == EXPECTED_DECISION
