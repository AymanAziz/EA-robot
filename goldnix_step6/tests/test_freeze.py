import pytest

from goldnix_step6.freeze import freeze_run, verify_run


def test_failed_verdict_can_be_frozen_but_not_overwritten_and_detects_tampering(tmp_path):
    code = tmp_path / "goldnix_step6"
    code.mkdir()
    source = code / "example.py"
    source.write_text("value = 1\n")
    run = code / "out" / "V2"
    run.mkdir(parents=True)
    (run / "metrics.json").write_text('{"verdict":"FAIL"}\n')
    freeze_run(tmp_path, run, verdict="FAIL", code_commit="abc", configs={"threshold": 50})
    assert verify_run(tmp_path, run)
    with pytest.raises(FileExistsError):
        freeze_run(tmp_path, run, verdict="PASS", code_commit="abc", configs={})
    source.write_text("value = 2\n")
    assert not verify_run(tmp_path, run)


def test_freeze_detects_modified_metrics(tmp_path):
    code = tmp_path / "goldnix_step6"
    code.mkdir()
    run = code / "out"
    run.mkdir()
    metrics = run / "metrics.json"
    metrics.write_text('{"verdict":"FAIL"}\n')
    freeze_run(tmp_path, run, verdict="FAIL", code_commit="abc", configs={})
    metrics.write_text('{"verdict":"PASS"}\n')
    assert not verify_run(tmp_path, run)
