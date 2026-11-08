"""Tests for signals/aroon.py. T1-T7 are the agreed contract; T8+ are guards."""
import numpy as np
import pytest

from signals.aroon import (PERIOD, TIES_MODES, aroon, aroon_osc,
                           aroon_osc_series, aroon_series)

N, END = 300, 250
FRESH, OLDEST = 100.0, 100.0 / PERIOD  # 100.0 and 1.43


def flat():
    """Flat high=1.0 / low=0.5 everywhere; tests add one extreme."""
    return np.ones(N), np.full(N, 0.5)


def with_high(bars_back, value=2.0):
    h, l = flat()
    h[END - bars_back] = value
    return h, l


def with_low(bars_back, value=0.1):
    h, l = flat()
    l[END - bars_back] = value
    return h, l


# ---- T1-T7: the agreed contract ------------------------------------------

def test_t1_fresh_high_is_100():
    assert aroon(*with_high(0), END)[0] == pytest.approx(FRESH)


def test_t2_high_69_back_is_1_43():
    assert aroon(*with_high(69), END)[0] == pytest.approx(OLDEST)
    assert round(aroon(*with_high(69), END)[0], 2) == 1.43


def test_t3_mixed_oscillator_is_98_57():
    h, _ = with_high(0)
    _, l = with_low(69)
    assert aroon_osc(h, l, END) == pytest.approx(FRESH - OLDEST)
    assert round(aroon_osc(h, l, END), 2) == 98.57


def test_t4_flat_top_oldest_is_1_43():
    h, l = np.full(N, 2.0), np.full(N, 0.5)
    assert aroon(h, l, END, ties="oldest")[0] == pytest.approx(OLDEST)


def test_t5_flat_top_newest_is_100():
    h, l = np.full(N, 2.0), np.full(N, 0.5)
    assert aroon(h, l, END, ties="newest")[0] == pytest.approx(FRESH)


def test_t6_bad_ties_raises():
    h, l = flat()
    with pytest.raises(ValueError):
        aroon(h, l, END, ties="Newest")
    with pytest.raises(ValueError):
        aroon_series(h, l, ties="Newest")


def test_t7_up_non_increasing_as_extreme_ages():
    ups = [aroon(*with_high(k), END)[0] for k in range(PERIOD)]
    assert all(b <= a for a, b in zip(ups, ups[1:]))
    assert ups[0] == pytest.approx(FRESH) and ups[-1] == pytest.approx(OLDEST)


# ---- T8+: guards ------------------------------------------------------------

def test_t8_down_side_mirrors_up_side():
    assert aroon(*with_low(0), END)[1] == pytest.approx(FRESH)
    assert aroon(*with_low(69), END)[1] == pytest.approx(OLDEST)


def test_t9_extreme_just_outside_window_is_ignored():
    h, l = with_high(70)              # 70 bars back = outside a 70-bar window
    h[END] = 1.5                      # in-window maximum on the newest bar
    assert aroon(h, l, END)[0] == pytest.approx(FRESH)


def test_t10_average_ties_flat_top():
    h, l = np.full(N, 2.0), np.full(N, 0.5)
    # mean bars_back over 0..69 = 34.5 -> 100 * (70 - 34.5) / 70
    assert aroon(h, l, END, ties="average")[0] == pytest.approx(100 * 35.5 / 70)


def test_t11_end_bounds():
    h, l = flat()
    aroon(h, l, PERIOD - 1)           # first valid index
    with pytest.raises(ValueError):
        aroon(h, l, PERIOD - 2)
    with pytest.raises(ValueError):
        aroon(h, l, N)


def test_t12_non_finite_in_window_raises():
    h, l = flat()
    h[END - 10] = np.nan
    with pytest.raises(ValueError):
        aroon(h, l, END)


def test_t13_length_mismatch_raises():
    with pytest.raises(ValueError):
        aroon(np.ones(100), np.ones(99), 80)


def test_t14_other_period():
    h, l = with_high(0)
    assert aroon(h, l, END, period=14)[0] == pytest.approx(100.0)
    h, l = with_high(13)
    assert aroon(h, l, END, period=14)[0] == pytest.approx(100.0 / 14)


@pytest.mark.parametrize("ties", TIES_MODES)
def test_t15_series_matches_scalar_with_ties(ties):
    rng = np.random.default_rng(42)
    close = 1000 + np.cumsum(rng.normal(0, 1, 2000))
    high = np.round(close + np.abs(rng.normal(0, 0.6, 2000)), 0)  # rounding forces ties
    low = np.round(close - np.abs(rng.normal(0, 0.6, 2000)), 0)
    up, dn = aroon_series(high, low, ties=ties)
    assert np.isnan(up[:PERIOD - 1]).all() and np.isnan(dn[:PERIOD - 1]).all()
    for t in range(PERIOD - 1, 2000):
        su, sd = aroon(high, low, t, ties=ties)
        assert up[t] == pytest.approx(su) and dn[t] == pytest.approx(sd)


def test_t16_oscillator_bounds():
    rng = np.random.default_rng(7)
    close = 1000 + np.cumsum(rng.normal(0, 1, 5000))
    osc = aroon_osc_series(close + 0.5, close - 0.5)
    valid = osc[PERIOD - 1:]
    limit = 100.0 - 100.0 / PERIOD
    assert np.all(valid <= limit + 1e-9) and np.all(valid >= -limit - 1e-9)


def test_t17_short_series_returns_all_nan():
    up, dn = aroon_series(np.ones(10), np.ones(10))
    assert np.isnan(up).all() and np.isnan(dn).all()
