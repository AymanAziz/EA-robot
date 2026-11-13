import pytest

from goldnix_p01.statistics import monthly_bootstrap


def test_months_are_resampled_as_whole_blocks_not_individual_trades():
    result = monthly_bootstrap(
        [1.0, 1.0, -4.0],
        ["2024-01", "2024-01", "2024-02"],
        calendar=["2024-01", "2024-02"],
        resamples=10000,
        seed=17,
    )
    assert result["mean_r"] == pytest.approx(-2 / 3)
    assert result["lower_5pct_r"] == -4
    assert result["upper_95pct_r"] == 1
    assert result["months"] == 2
    assert result["resamples"] == 10000


def test_chunked_monte_carlo_matches_existing_small_exact_reference():
    from metrics.montecarlo import monte_carlo_drawdown
    from goldnix_p01.statistics import chunked_drawdown

    values = [-0.03, 0.02, 0.01, -0.01]
    expected = monte_carlo_drawdown(values, trades_per_year=30, simulations=1000, seed=91)
    actual = chunked_drawdown(values, trades_per_year=30, simulations=1000, seed=91, chunk_size=7)
    assert actual["p99_drawdown_usd"] == expected.p99_max_drawdown_usd
    assert actual["paths"] == 1000


def test_drawdown_includes_loss_from_starting_equity():
    from goldnix_p01.statistics import chunked_drawdown

    result = chunked_drawdown([-0.03], trades_per_year=3, simulations=20, seed=1)
    assert result["p99_drawdown_usd"] == pytest.approx(0.09)


def test_unknown_returns_cannot_silently_become_a_bootstrap_pass():
    with pytest.raises(ValueError):
        monthly_bootstrap([float("nan")], ["2024-01"], calendar=["2024-01"], resamples=100, seed=1)
