"""Aroon indicator for the H1 Aroon breakout study.

Conventions (read these before changing anything)
-------------------------------------------------
* Arrays run oldest -> newest: index 0 is the oldest bar.
* ``end`` is the index of the last CLOSED bar in the window.
* The window is bars ``end - period + 1 .. end`` inclusive (``period`` bars).
* ``bars_back`` is 0 for the newest bar in the window and ``period - 1`` for
  the oldest one.
* Aroon Up   = 100 * (period - bars_back_of_highest_high) / period
  Aroon Down = 100 * (period - bars_back_of_lowest_low)  / period
  With period = 70: 100.0 when the extreme is on the newest bar,
  1.43 (= 100/70) when it is 69 bars back.

Ties (several bars share the extreme)
-------------------------------------
* ``"newest"``  - use the most recent bar holding the extreme.
* ``"oldest"``  - use the oldest bar holding the extreme.
* ``"average"`` - use the mean bars_back of all bars holding the extreme.
Any other value raises ``ValueError``. The MQL5 EA must implement the same
rule with an explicit loop so that Python and MT5 agree by construction.
"""
from __future__ import annotations

from typing import Literal

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

PERIOD = 70
THRESHOLD = 50.0
TIES_MODES = ("newest", "oldest", "average")
Ties = Literal["newest", "oldest", "average"]


def _check_ties(ties: str) -> None:
    if ties not in TIES_MODES:
        raise ValueError(f"ties={ties!r}; expected one of {TIES_MODES}")


def _as_series(high, low) -> tuple[np.ndarray, np.ndarray]:
    high = np.asarray(high, dtype=float)
    low = np.asarray(low, dtype=float)
    if high.ndim != 1 or low.ndim != 1:
        raise ValueError("high and low must be 1-D")
    if high.shape != low.shape:
        raise ValueError(f"length mismatch: high={high.size}, low={low.size}")
    return high, low


def _bars_back(window: np.ndarray, find_max: bool, ties: str) -> float:
    """Bars back (0 = newest) of the window's extreme under the tie rule."""
    extreme = window.max() if find_max else window.min()
    positions = np.flatnonzero(window == extreme)  # positions from the oldest bar
    if ties == "oldest":
        pos = float(positions[0])
    elif ties == "newest":
        pos = float(positions[-1])
    else:  # "average"; validity already checked
        pos = float(positions.mean())
    return (window.size - 1) - pos


def aroon(high, low, end: int, period: int = PERIOD,
          ties: Ties = "newest") -> tuple[float, float]:
    """Aroon (up, down) for the window ending at closed bar ``end``."""
    _check_ties(ties)
    high, low = _as_series(high, low)
    if period < 2:
        raise ValueError(f"period={period} must be >= 2")
    if not isinstance(end, (int, np.integer)):
        raise TypeError(f"end must be an int, got {type(end).__name__}")
    if end < period - 1 or end >= high.size:
        raise ValueError(f"end={end} outside [{period - 1}, {high.size - 1}]")
    wh = high[end - period + 1:end + 1]
    wl = low[end - period + 1:end + 1]
    if not (np.isfinite(wh).all() and np.isfinite(wl).all()):
        raise ValueError(f"non-finite price in window ending at {end}")
    up = 100.0 * (period - _bars_back(wh, True, ties)) / period
    dn = 100.0 * (period - _bars_back(wl, False, ties)) / period
    return up, dn


def aroon_osc(high, low, end: int, period: int = PERIOD,
              ties: Ties = "newest") -> float:
    """Aroon oscillator = up - down, in [-(100 - 100/period), +(100 - 100/period)]."""
    up, dn = aroon(high, low, end, period, ties)
    return up - dn


def _bars_back_rows(windows: np.ndarray, find_max: bool, ties: str) -> np.ndarray:
    """Vectorised _bars_back over rows of a (n_windows, period) array."""
    n = windows.shape[1]
    if ties == "newest":
        rev = windows[:, ::-1]  # column 0 = newest bar = 0 bars back
        return (rev.argmax(1) if find_max else rev.argmin(1)).astype(float)
    if ties == "oldest":
        pos = windows.argmax(1) if find_max else windows.argmin(1)
        return (n - 1) - pos.astype(float)
    extreme = windows.max(1, keepdims=True) if find_max else windows.min(1, keepdims=True)
    mask = windows == extreme
    pos = (mask * np.arange(n)).sum(1) / mask.sum(1)
    return (n - 1) - pos


def aroon_series(high, low, period: int = PERIOD,
                 ties: Ties = "newest") -> tuple[np.ndarray, np.ndarray]:
    """Aroon (up, down) for every bar; the first ``period - 1`` values are NaN.

    Element ``t`` equals ``aroon(high, low, t, period, ties)``.
    """
    _check_ties(ties)
    high, low = _as_series(high, low)
    if period < 2:
        raise ValueError(f"period={period} must be >= 2")
    up = np.full(high.size, np.nan)
    dn = np.full(high.size, np.nan)
    if high.size < period:
        return up, dn
    if not (np.isfinite(high).all() and np.isfinite(low).all()):
        raise ValueError("non-finite prices; clean the data before computing Aroon")
    wh = sliding_window_view(high, period)
    wl = sliding_window_view(low, period)
    up[period - 1:] = 100.0 * (period - _bars_back_rows(wh, True, ties)) / period
    dn[period - 1:] = 100.0 * (period - _bars_back_rows(wl, False, ties)) / period
    return up, dn


def aroon_osc_series(high, low, period: int = PERIOD,
                     ties: Ties = "newest") -> np.ndarray:
    up, dn = aroon_series(high, low, period, ties)
    return up - dn
