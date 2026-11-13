import numpy as np
import pytest

from goldnix_p01.data import TICK_DTYPE, validate_ticks, minute_bars


def test_quote_side_extrema_are_aggregated_before_midpoint():
    ticks = np.array([(1000, 100, 110), (2000, 101, 102)], dtype=TICK_DTYPE)
    bars = minute_bars(ticks)
    assert bars.iloc[0].mid_high == 105.5
    assert bars.iloc[0].mid_low == 101


def test_same_millisecond_quotes_keep_input_order():
    ticks = np.array([(1000, 100, 101), (1000, 102, 103)], dtype=TICK_DTYPE)
    assert validate_ticks(ticks)["ticks"] == 2
    assert minute_bars(ticks).iloc[0].bid_close == 102


def test_missing_minutes_are_not_fabricated():
    ticks = np.array([(1000, 100, 101), (121000, 100, 101)], dtype=TICK_DTYPE)
    assert minute_bars(ticks).epoch_seconds.tolist() == [0, 120]


@pytest.mark.parametrize("values", [[(2000, 100, 101), (1000, 100, 101)], [(1000, 101, 100)], [(1000, 0, 1)]])
def test_bad_chronology_or_quotes_rejected(values):
    with pytest.raises(ValueError):
        validate_ticks(np.array(values, dtype=TICK_DTYPE))
