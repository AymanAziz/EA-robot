import numpy as np
import pandas as pd

from goldnix_p02.features import higher_trend


def test_higher_trend_is_not_available_until_the_entire_candle_closes():
    bars = pd.DataFrame(
        {"epoch_seconds": np.arange(9) * 60, "mid_close": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 99.0, 99.0, 99.0]}
    )
    result = higher_trend(bars, minutes=3, period=2, slope_bars=1, warmup=3)
    assert result["direction"].tolist() == [0, 0, 0, 0, 0, 0, 0, 0, 1]
    assert result["ready"].tolist() == [False] * 8 + [True]


def test_missing_minute_invalidates_whole_higher_candle():
    bars = pd.DataFrame({"epoch_seconds": np.arange(12) * 60, "mid_close": np.arange(12) + 100.0})
    bars = bars.drop(index=4).reset_index(drop=True)
    result = higher_trend(bars, minutes=3, period=2, slope_bars=1, warmup=3)
    assert result["complete_bars"] == 3
    assert not result["ready"][bars.epoch_seconds.eq(8 * 60)].any()
    assert result["ready"][-1]


def test_missing_higher_candle_expires_previous_trend_until_next_complete_close():
    bars = pd.DataFrame({"epoch_seconds": np.arange(18) * 60, "mid_close": np.arange(18) + 100.0})
    bars = bars.drop(index=10).reset_index(drop=True)
    result = higher_trend(bars, minutes=3, period=2, slope_bars=1, warmup=3)
    by_open = dict(zip(bars.epoch_seconds, result["ready"]))
    assert by_open[8 * 60]
    assert by_open[9 * 60]
    assert not by_open[11 * 60]
    assert not by_open[13 * 60]
    assert by_open[14 * 60]


def test_future_append_cannot_change_past_trend_and_sells_mirror_buys():
    bars = pd.DataFrame({"epoch_seconds": np.arange(240) * 60, "mid_close": np.arange(240) * 0.1 + 100})
    prefix = higher_trend(bars.iloc[:90], minutes=15, period=3, slope_bars=1, warmup=4)
    full = higher_trend(bars, minutes=15, period=3, slope_bars=1, warmup=4)
    reflected = bars.copy()
    reflected["mid_close"] = 300 - bars.mid_close
    sell = higher_trend(reflected, minutes=15, period=3, slope_bars=1, warmup=4)
    np.testing.assert_array_equal(prefix["direction"], full["direction"][:90])
    np.testing.assert_array_equal(prefix["available_at"], full["available_at"][:90])
    assert full["direction"][-1] == 1
    np.testing.assert_array_equal(sell["direction"], -full["direction"])


def test_filters_only_suppress_entries_and_weak_close_is_rejected():
    from goldnix_p02.features import filter_features

    n = 7000
    close = 100 + np.arange(n) * 0.001
    bars = pd.DataFrame(
        {
            "epoch_seconds": np.arange(n) * 60,
            "mid_close": close,
            "mid_high": close + 0.01,
            "mid_low": close - 0.01,
            "direction": np.resize([-1, 0, 1], n),
        }
    )
    both = filter_features(bars, "P04_BOTH")
    assert both.direction.eq(1).any()
    assert not both.direction.eq(-1).any()
    assert np.all((both.direction == 0) | (both.direction == bars.direction))
    assert not filter_features(bars, "P05_BOTH_CLOSE").direction.any()


def test_preceding_context_warms_trend_without_trading_or_observing_future_bars():
    from goldnix_p02.features import filter_features
    import pytest

    n = 7000
    close = 100 + np.arange(n) * 0.001
    all_bars = pd.DataFrame(
        {
            "epoch_seconds": np.arange(n) * 60,
            "mid_close": close,
            "mid_high": close + 0.01,
            "mid_low": close - 0.01,
            "direction": np.ones(n, dtype=int),
        }
    )
    current = all_bars.iloc[6500:].reset_index(drop=True)
    history = all_bars.iloc[:6500].copy()
    result = filter_features(current, "P04_BOTH", history=history)
    assert len(result) == len(current)
    assert result.direction.iloc[0] == 1
    assert result.epoch_seconds.min() == 6500 * 60
    with pytest.raises(ValueError, match="earlier"):
        filter_features(current, "P04_BOTH", history=all_bars.iloc[:6501])
