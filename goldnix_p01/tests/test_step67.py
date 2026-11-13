from goldnix_p01.step67 import holdout_preflight


def test_engineering_parity_does_not_unlock_holdout():
    step6 = {
        "candidate": "M1_PROFIT_PROTECTION_P01",
        "formal_qualified": False,
        "engineering_passed": True,
        "gates": {},
        "source_sha256": {"ea": "abc"},
    }
    result = holdout_preflight(
        step6, current_source={"ea": "abc"}, freeze_verified=False, holdout_window=None, consumed_windows=[]
    )
    assert result["status"] == "BLOCKED_PREREQUISITES"
    assert "step6_not_qualified" in result["blockers"]
    assert result["holdout_payload_read"] is False
    assert result["formal_passed"] is False


def test_consumed_holdout_is_rejected_even_with_passing_step6_metadata():
    step6 = {
        "candidate": "M1_PROFIT_PROTECTION_P01",
        "formal_qualified": True,
        "gates": {f"G{i}": {"formal_passed": True} for i in range(1, 10)},
        "source_sha256": {"ea": "abc"},
    }
    result = holdout_preflight(
        step6,
        current_source={"ea": "abc"},
        freeze_verified=True,
        holdout_window=("2026-01-01T00:00:00Z", "2026-02-01T00:00:00Z"),
        consumed_windows=[("2026-01-01T00:00:00Z", "2026-10-01T00:00:00Z")],
    )
    assert result["blockers"] == ["holdout_period_already_consumed"]
    assert result["holdout_payload_read"] is False


def test_changed_candidate_source_blocks_holdout_preflight():
    step6 = {
        "candidate": "M1_PROFIT_PROTECTION_P01",
        "formal_qualified": True,
        "gates": {f"G{i}": {"formal_passed": True} for i in range(1, 10)},
        "source_sha256": {"ea": "old"},
    }
    result = holdout_preflight(
        step6,
        current_source={"ea": "new"},
        freeze_verified=True,
        holdout_window=("2030-01-01T00:00:00Z", "2030-02-01T00:00:00Z"),
        consumed_windows=[],
    )
    assert result["blockers"] == ["candidate_source_changed_or_missing"]
    assert result["holdout_payload_read"] is False
