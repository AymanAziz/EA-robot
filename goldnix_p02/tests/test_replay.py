import numpy as np

from goldnix_p01.data import TICK_DTYPE
from goldnix_p01.engine import Contract
from goldnix_p01.replay import TIMER_DTYPE, replay as original
from goldnix_p02.replay import replay


def test_unfiltered_fork_reproduces_p01_entry_protection_and_exit():
    start = 1706749200
    rows = []
    for minute in range(104):
        price = 100 if minute < 100 else 99 if minute < 102 else 101
        rows.extend(
            [
                (1000 * (start + 60 * minute), price, price + 0.1),
                (1000 * (start + 60 * minute + 20), price + 0.2, price + 0.3),
                (1000 * (start + 60 * minute + 40), price - 0.2, price - 0.1),
            ]
        )
    ticks = np.array(rows, dtype=TICK_DTYPE)
    timers = np.zeros(104 * 60 - 1, dtype=TIMER_DTYPE)
    timers["utc"] = np.arange(start + 1, start + 104 * 60)
    indices = np.searchsorted(ticks["utc_ms"], timers["utc"] * 1000, side="right") - 1
    timers["quote_ms"] = ticks["utc_ms"][indices]
    timers["bid"] = ticks["bid"][indices]
    timers["ask"] = ticks["ask"][indices]
    timers["end"] = start + 86400
    result = replay(ticks, timers, Contract(), offset=0, candidate="P01")
    assert len(result["trades"]) == 1
    assert result == original(ticks, timers, Contract(), offset=0)
