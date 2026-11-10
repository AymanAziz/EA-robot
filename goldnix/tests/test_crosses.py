"""Behaviour tests for closed-bar Aroon oscillator crossings."""

import numpy as np
import pytest

from signals.crosses import BUY, NONE, SELL, cross_series


def test_known_crossing_bars_are_aligned_with_the_closed_bar():
    oscillator = np.array([np.nan, -60.0, 40.0, 60.0, 55.0, -40.0, -60.0])

    signals = cross_series(oscillator)

    assert np.flatnonzero(signals == BUY).tolist() == [3]
    assert np.flatnonzero(signals == SELL).tolist() == [6]


def test_touching_the_exact_threshold_is_not_a_cross():
    oscillator = np.array([-60.0, 50.0, 60.0, 40.0, -50.0, -60.0])

    signals = cross_series(oscillator)

    assert signals.tolist() == [NONE] * len(oscillator)


def test_no_signal_exists_before_two_valid_aroon_values():
    oscillator = np.array([np.nan, np.nan, 60.0, 40.0, 60.0])

    signals = cross_series(oscillator)

    assert signals[:4].tolist() == [NONE, NONE, NONE, NONE]
    assert signals[4] == BUY


def test_non_1d_oscillator_is_rejected():
    with pytest.raises(ValueError, match="oscillator must be 1-D"):
        cross_series([[40.0, 60.0]])


@pytest.mark.parametrize("threshold", [0.0, -1.0])
def test_non_positive_threshold_is_rejected(threshold):
    with pytest.raises(ValueError, match="threshold must be greater than zero"):
        cross_series([40.0, 60.0], threshold=threshold)
