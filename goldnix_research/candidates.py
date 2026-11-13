"""Causal candidate signals on closed H1 bars, using the existing ATR contract."""

import numpy as np

from params.atr import atr_simple
from signals.aroon import aroon_osc_series
from signals.crosses import cross_series


def prepare_candidate(bars, candidate):
    """Add signals and direction eligibility without changing quote data."""
    frame = bars.copy()
    high = (frame.bid_high + frame.ask_high) / 2
    low = (frame.bid_low + frame.ask_low) / 2
    close = (frame.bid_close + frame.ask_close) / 2
    frame["atr"] = atr_simple(high.to_numpy(), low.to_numpy(), close.to_numpy(), period=14)
    if candidate["family"] == "aroon":
        oscillator = aroon_osc_series(high.to_numpy(), low.to_numpy(),
                                      period=candidate["period"], ties="newest")
        frame["signal"] = cross_series(oscillator, candidate["threshold"])
        frame["buy_eligible"] = True
        frame["sell_eligible"] = True
        return frame
    if candidate["family"] == "channel":
        period = candidate["period"]
        frame["buy_eligible"] = True
        frame["sell_eligible"] = True
        buy = close.gt(high.shift(1).rolling(period, min_periods=period).max())
        sell = close.lt(low.shift(1).rolling(period, min_periods=period).min())
        frame["signal"] = np.select([buy, sell], [1, -1], default=0).astype(np.int8)
        return frame
    if candidate["family"] != "pullback":
        raise ValueError(f"Unknown candidate family: {candidate['family']}")
    period = candidate["slow_period"]
    trend = close.ewm(span=period, adjust=False, min_periods=period).mean()
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=.5, adjust=False, min_periods=2).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=.5, adjust=False, min_periods=2).mean()
    total = gain + loss
    rsi = 100 * gain / total.where(total.ne(0))
    cut = candidate["rsi_cut"]
    frame["buy_eligible"] = close.gt(trend)
    frame["sell_eligible"] = close.lt(trend)
    buy = frame.buy_eligible & rsi.gt(cut) & rsi.shift(1).le(cut)
    sell = frame.sell_eligible & rsi.lt(100 - cut) & rsi.shift(1).ge(100 - cut)
    frame["signal"] = np.select([buy, sell], [1, -1], default=0).astype(np.int8)
    return frame
