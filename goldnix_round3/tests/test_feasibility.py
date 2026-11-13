import itertools

import numpy as np
import pytest

from goldnix_round3.feasibility import run_probability, drawdown_lower_bound


def test_probability_matches_exhaustive_independent_paths():
    p, trades, length = .3, 7, 3
    exact = 0.
    for path in itertools.product([0, 1], repeat=trades):
        if '1' * length in ''.join(map(str, path)):
            exact += p ** sum(path) * (1 - p) ** (trades - sum(path))
    assert run_probability(p, trades, length) == pytest.approx(exact)


def test_probability_boundaries():
    assert run_probability(0, 50, 3) == 0
    assert run_probability(1, 2, 3) == 0
    assert run_probability(1, 3, 3) == 1


def test_a_drawdown_exactly_at_limit_is_not_a_failure():
    result = drawdown_lower_bound(np.array([-1., 2.]), annual_trades=2, limit_usd=2.)
    assert result['breach_probability_lower_bound'] == 0
    result = drawdown_lower_bound(np.array([-1., 2.]), annual_trades=3, limit_usd=2.)
    assert result['breach_probability_lower_bound'] == pytest.approx(.125)
    assert result['g7_mathematically_incompatible_with_iid_distribution'] is True


def test_single_large_loss_alone_can_rule_out_p99_gate():
    result = drawdown_lower_bound(np.array([-3., 1., 1., 1.]), annual_trades=10, limit_usd=2.4)
    assert result['breach_probability_lower_bound'] == pytest.approx(1 - .75 ** 10)
    assert result['consecutive_losses'] == 1


def test_decimal_roundoff_cannot_turn_equal_drawdown_into_a_breach():
    result = drawdown_lower_bound(np.array([-.8, 1.]), annual_trades=3, limit_usd=2.4)
    assert result['breach_probability_lower_bound'] == 0


def test_bound_does_not_claim_a_pass_when_it_finds_no_failure():
    result = drawdown_lower_bound(np.array([1., 2.]), annual_trades=50, limit_usd=2.4)
    assert result['breach_probability_lower_bound'] == 0
    assert result['g7_mathematically_incompatible_with_iid_distribution'] is False
    assert result['approval'] is False
