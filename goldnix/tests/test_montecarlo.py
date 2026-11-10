"""Behaviour tests for one-year maximum-drawdown simulation."""

import pytest

from metrics.montecarlo import max_drawdown, monte_carlo_drawdown


def test_max_drawdown_includes_starting_equity_peak():
    assert max_drawdown([2.0, -1.0, -3.0, 4.0]) == pytest.approx(4.0)


def test_constant_loss_paths_have_exact_p99_drawdown():
    result = monte_carlo_drawdown(
        [-1.0],
        trades_per_year=3,
        simulations=100,
        seed=11,
    )

    assert result.p99_max_drawdown_usd == pytest.approx(3.0)
    assert result.trades_per_year == 3
    assert result.simulations == 100
