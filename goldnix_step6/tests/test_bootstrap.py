import pandas as pd
import pytest

from goldnix_step6.bootstrap import paired_month_bootstrap


def test_same_month_resampling_preserves_exact_paired_edge_and_empty_months():
    signal = pd.DataFrame({"exit_ts": pd.to_datetime(["2025-01-05", "2025-03-05"], utc=True),
                           "r_multiple": [10.0, -10.0]})
    baseline = signal.copy()
    baseline["r_multiple"] = [9.0, -11.0]
    baseline["draw"] = 0
    result = paired_month_bootstrap(signal, baseline, start="2025-01-01", end="2025-03-31",
                                   resamples=1000, seed=7)
    assert result["mean_r"] == 0.0
    assert result["edge_point"] == pytest.approx(1.0)
    assert result["edge_lower"] == pytest.approx(1.0)
    assert result["months"] == 3
    assert result["zero_trade_months"] == 1
    assert result["empty_resamples_rejected"] > 0


def test_edge_bound_targets_the_average_of_baseline_draws_not_one_random_path():
    signal = pd.DataFrame({"exit_ts": pd.to_datetime(["2025-01-05"], utc=True), "r_multiple": [0.]})
    baseline = pd.DataFrame({"exit_ts": pd.to_datetime(["2025-01-05"]*200, utc=True),
                             "r_multiple": [-1., 1.]*100, "draw": range(200)})
    result = paired_month_bootstrap(signal, baseline, start="2025-01-01", end="2025-01-31",
                                   resamples=1000, seed=7)
    assert result["edge_point"] == 0.
    assert -0.30 < result["edge_lower"] < 0.
