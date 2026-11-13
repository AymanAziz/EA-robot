import pandas as pd
import pytest

from goldnix_research.screen import screen_statistics, screen_candidate
from goldnix_research.tests.test_candidates import bars
from params.config import load_yaml
from pathlib import Path


def test_bootstrap_retains_empty_calendar_months_and_reports_selection_bound():
    trades = pd.DataFrame({"exit_ts": ["2020-01-06T01:00Z", "2020-03-06T01:00Z"],
                           "r_multiple": [1., 3.]})
    stats = screen_statistics(trades, start="2020-01-01", end="2020-03-31",
                              trials=24, resamples=10000, seed=20261110)
    assert stats["months"] == 3
    assert stats["empty_months"] == 1
    assert stats["mean_r"] == pytest.approx(2)
    assert stats["mean_lower"] == pytest.approx(1)
    assert stats["selection_lower"] == pytest.approx(1)
    assert stats["empty_resamples_rejected"] > 0


def test_screen_keeps_failed_candidates_and_does_not_call_them_approved():
    eras = {}
    for name, date in zip("ABCD", ["2005-06-06", "2011-09-05", "2016-01-04", "2021-01-04"]):
        frame = bars([100, 101, 102, 104, 99, 100, 101, 105, 99] * 5)
        frame["timestamp_utc"] = pd.date_range(date, periods=len(frame), freq="h", tz="UTC")
        frame["era"] = name
        eras[name] = frame
    config = load_yaml(Path(__file__).resolve().parents[2] / "goldnix/params/decision.yaml")
    candidate = {"id": "TEST", "family": "channel", "period": 3, "stop_atr": 1, "reward_ratio": 2}
    protocol = {"trial_count": 24, "bootstrap_resamples": 100, "bootstrap_seed": 20261110}
    result, trades = screen_candidate(eras, candidate, config, protocol)
    assert result["id"] == "TEST"
    assert result["baskets"] > 0
    assert result["G5"] is False
    assert result["eligible_for_full_evaluation"] is False
    assert result["approval"] == "EXPLORATORY_ONLY"
    assert set(trades.era) == set("ABCD")
