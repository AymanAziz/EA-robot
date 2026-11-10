"""Behaviour tests for monthly block bootstrap confidence bounds."""

import pandas as pd
import pytest

from metrics.bootstrap import monthly_block_bootstrap


def test_one_month_bootstrap_has_exact_mean_zero_se_and_edge_bound():
    trades = pd.DataFrame(
        {
            "exit_ts": pd.to_datetime(
                ["2025-01-02T00:00:00Z", "2025-01-20T00:00:00Z"], utc=True
            ),
            "r_multiple": [1.0, 3.0],
        }
    )

    result = monthly_block_bootstrap(
        trades,
        resamples=100,
        seed=7,
        baseline_draw_means=[0.5],
    )

    assert result.point_estimate == pytest.approx(2.0)
    assert result.standard_error == pytest.approx(0.0)
    assert result.lower_bound == pytest.approx(2.0)
    assert result.edge_point_estimate == pytest.approx(1.5)
    assert result.edge_lower_bound == pytest.approx(1.5)
    assert result.resamples == 100
