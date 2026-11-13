import hashlib
import gzip
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from gates.freeze import write_freeze
from goldnix_step6.freeze import freeze_run
from params.config import load_yaml
import yaml
from goldnix_step7.runner import run_once

REPO = Path(__file__).resolve().parents[2]


def bars(start, end):
    times = pd.date_range(start, end, freq="h", tz="UTC", inclusive="left")
    price = 2000 + np.random.default_rng(17).normal(size=len(times)).cumsum()
    return pd.DataFrame({
        "timestamp_utc": times, "epoch_seconds": times.asi8 // 1_000_000_000,
        "bid_open": price, "bid_high": price + 2, "bid_low": price - 2, "bid_close": price,
        "ask_open": price + 0.1, "ask_high": price + 2.1,
        "ask_low": price - 1.9, "ask_close": price + 0.1, "provider_volume": 1.,
    })


@pytest.fixture
def study(tmp_path):
    for relative in ("goldnix/params/decision.yaml", "goldnix_v2/decision.yaml",
                     "goldnix/data/eras.yaml"):
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((REPO / relative).read_bytes())
    training = bars("2025-12-01", "2026-01-01")
    hashes = {}
    for kind in ("raw", "clean"):
        path = tmp_path / "goldnix/data" / kind / "xauusd_h1_20030505_20251231_bid_ask.csv"
        path.parent.mkdir(parents=True)
        training.to_csv(path, index=False)
        hashes[kind] = hashlib.sha256(path.read_bytes()).hexdigest()
    write_freeze(tmp_path / "goldnix", code_commit="fixture", verdict="FAIL")
    for version, directory, config_path in (
        ("V1", "V1_4b823fa2ca89", "goldnix/params/decision.yaml"),
        ("V2", "V2_f8bd017f3802", "goldnix_v2/decision.yaml"),
    ):
        run = tmp_path / "goldnix_step6/out" / directory
        run.mkdir(parents=True)
        metrics = {"study": version, "verdict": "FAIL", "data_sha256": hashes,
                   "pooled": {"mean_r": 0.1, "bootstrap": {"standard_error": 0.1}},
                   "gates": {f"G{i}": {"passed": False} for i in range(1, 10)}}
        (run / "metrics.json").write_text(json.dumps(metrics))
        freeze_run(tmp_path, run, verdict="FAIL", code_commit="fixture",
                   configs={"decision": load_yaml(tmp_path / config_path)})
    source = tmp_path / "holdout.csv"
    bars("2026-01-01", "2026-10-01").to_csv(source, index=False)
    return tmp_path, source


def test_missing_freeze_refuses_before_opening_even_a_missing_holdout(tmp_path):
    with pytest.raises(PermissionError, match="freeze|FROZEN"):
        run_once(tmp_path, tmp_path / "missing.csv")


@pytest.mark.parametrize("relative", [
    "goldnix_v2/decision.yaml",
    "goldnix_step6/out/V2_f8bd017f3802/metrics.json",
    "goldnix/data/clean/xauusd_h1_20030505_20251231_bid_ask.csv",
])
def test_changed_config_statistics_or_warmup_refuses_before_holdout(study, relative):
    root, _ = study
    with (root / relative).open("a") as handle:
        handle.write("\n# changed\n")
    with pytest.raises(PermissionError, match="freeze|hash"):
        run_once(root, root / "missing.csv")


def test_both_frozen_strategies_run_once_with_warmup_excluded_and_no_step8_approval(study):
    root, source = study
    result = run_once(root, source)
    assert result["status"] == "COMPLETE"
    assert set(result["studies"]) == {"V1", "V2"}
    for version, outcome in result["studies"].items():
        assert outcome["baskets"] >= 2
        assert outcome["step8_permitted"] is False
        trades = pd.read_csv(root / "goldnix_step7/out" / version / "trades.csv")
        assert pd.to_datetime(trades.entry_ts, utc=True).min() >= pd.Timestamp("2026-01-01T00:00Z")
        assert pd.to_datetime(trades.exit_ts, utc=True).max() < pd.Timestamp("2026-10-01T00:00Z")
    with pytest.raises(FileExistsError, match="once|attempt|consumed"):
        run_once(root, source)


@pytest.mark.parametrize("problem", ["duplicate", "unsorted", "negative_spread", "bad_ohlc",
                                    "nan", "overlap", "partial", "naive", "epoch", "subhour"])
def test_invalid_holdout_is_rejected_without_repair_and_consumes_the_attempt(study, problem):
    root, source = study
    data = pd.read_csv(source)
    if problem == "duplicate":
        data = pd.concat([data.iloc[:1], data], ignore_index=True)
    elif problem == "unsorted":
        data = data.iloc[::-1]
    elif problem == "negative_spread":
        data.loc[0, "ask_open"] = data.loc[0, "bid_open"] - 0.1
    elif problem == "bad_ohlc":
        data.loc[0, "bid_low"] = data.loc[0, "bid_high"] + 1
    elif problem == "nan":
        data.loc[0, "ask_high"] = float("nan")
    elif problem == "overlap":
        data.loc[0, "timestamp_utc"] = "2025-12-31T23:00:00+00:00"
    elif problem == "partial":
        data = data.iloc[:24]
    elif problem == "naive":
        data["timestamp_utc"] = data.timestamp_utc.str.replace("+00:00", "", regex=False)
    elif problem == "epoch":
        data.loc[0, "epoch_seconds"] += 3600
    elif problem == "subhour":
        data.loc[0, "timestamp_utc"] = "2026-01-01T00:30:00+00:00"
    data.to_csv(source, index=False)
    with pytest.raises(ValueError):
        run_once(root, source)
    with pytest.raises(FileExistsError, match="once|attempt|consumed"):
        run_once(root, source)


def test_native_provider_download_is_snapshotted_with_hash_and_runner_provenance(study):
    root, source = study
    frame = pd.read_csv(source).drop(columns="timestamp_utc").rename(columns={
        "epoch_seconds": "ts", "bid_open": "o", "bid_high": "h", "bid_low": "l", "bid_close": "c",
        "ask_open": "ao", "ask_high": "ah", "ask_low": "al", "ask_close": "ac", "provider_volume": "v",
    })
    source = root / "2026.json.gz"
    payload = gzip.compress(frame.to_json(orient="records").encode(), mtime=0)
    source.write_bytes(payload)
    result = run_once(root, source)
    assert result["input"]["sha256"] == hashlib.sha256(payload).hexdigest()
    assert (root / result["input"]["snapshot"]).read_bytes() == payload
    assert "runner.py" in result["protocol"]["step7_source_sha256"]
    assert "data.py" in result["protocol"]["step7_source_sha256"]


def test_freeze_config_copy_cannot_override_the_hashed_strategy_config(study):
    root, _ = study
    path = root / "goldnix_step6/out/V2_f8bd017f3802/FROZEN.yaml"
    frozen = load_yaml(path)
    frozen["configs"]["decision"]["threshold"] = 10
    path.write_text(yaml.safe_dump(frozen))
    with pytest.raises(PermissionError, match="config"):
        run_once(root, root / "missing.csv")


def test_missing_input_does_not_consume_the_real_evaluation(study):
    root, source = study
    with pytest.raises(FileNotFoundError, match="not consumed"):
        run_once(root, root / "missing.csv")
    assert run_once(root, source)["status"] == "COMPLETE"


def test_failure_after_access_is_auditable_and_cannot_be_retried(study):
    root, source = study
    source.write_text("not a dataset\n")
    with pytest.raises(ValueError):
        run_once(root, source)
    failure = json.loads((root / "goldnix_step7/out/ERROR.json").read_text())
    assert failure["status"] == "FAILED_AFTER_ACCESS"
    assert failure["holdout_consumed"] is True
    with pytest.raises(FileExistsError):
        run_once(root, source)
