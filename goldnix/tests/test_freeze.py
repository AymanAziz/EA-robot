"""Behaviour tests for immutable research freeze and holdout locking."""

from pathlib import Path

import pytest

from gates.freeze import assert_holdout_unlocked, verify_freeze, write_freeze
from ingest.holdout import load_holdout


def _research_tree(tmp_path: Path) -> Path:
    root = tmp_path / "goldnix"
    (root / "params").mkdir(parents=True)
    (root / "sim").mkdir()
    (root / "params" / "decision.yaml").write_text("threshold: 50\n", encoding="utf-8")
    (root / "sim" / "engine.py").write_text("VALUE = 1\n", encoding="utf-8")
    return root


def test_holdout_unlock_requires_exact_frozen_config_and_code(tmp_path):
    root = _research_tree(tmp_path)

    with pytest.raises(PermissionError, match="FROZEN.yaml"):
        assert_holdout_unlocked(root)

    write_freeze(root, code_commit="abc123", verdict="FAIL")

    assert verify_freeze(root) is True
    assert_holdout_unlocked(root)

    (root / "sim" / "engine.py").write_text("VALUE = 2\n", encoding="utf-8")
    assert verify_freeze(root) is False
    with pytest.raises(PermissionError, match="hash mismatch"):
        assert_holdout_unlocked(root)


def test_holdout_loader_checks_freeze_before_reading_file(tmp_path):
    root = _research_tree(tmp_path)
    holdout = root / "data" / "holdout" / "bars.csv"
    holdout.parent.mkdir(parents=True)
    holdout.write_text("timestamp_utc,value\n2026-01-01T00:00:00Z,1\n", encoding="utf-8")

    with pytest.raises(PermissionError, match="FROZEN.yaml"):
        load_holdout(holdout, root=root)

    write_freeze(root, code_commit="abc123", verdict="FAIL")

    loaded = load_holdout(holdout, root=root)
    assert loaded["value"].tolist() == [1]
