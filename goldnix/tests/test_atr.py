"""Hand-computed tests for ATR candidates used by the parity harness."""

import numpy as np
import pytest

from params.atr import atr_simple, atr_wilder, true_range


def test_true_range_and_both_atr_methods_match_worked_example():
    high = np.array([10.0, 12.0, 13.0, 15.0, 14.0])
    low = np.array([8.0, 9.0, 11.0, 12.0, 10.0])
    close = np.array([9.0, 11.0, 12.0, 13.0, 11.0])

    tr = true_range(high, low, close)
    simple = atr_simple(high, low, close, period=3)
    wilder = atr_wilder(high, low, close, period=3)

    assert tr.tolist() == pytest.approx([2.0, 3.0, 2.0, 3.0, 4.0])
    assert np.isnan(simple[:2]).all()
    assert simple[2:].tolist() == pytest.approx([7 / 3, 8 / 3, 3.0])
    assert np.isnan(wilder[:2]).all()
    assert wilder[2:].tolist() == pytest.approx([7 / 3, 23 / 9, 82 / 27])
