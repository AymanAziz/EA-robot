"""Recorded rejection signals and tighter eligibility; no quote changes."""

import numpy as np

from goldnix_research.candidates import prepare_candidate
from goldnix_research.risk_budget import apply_risk_budget


def prepare_round2(bars, candidate):
    base = {**candidate, "family": "channel" if candidate["family"] == "rejection" else candidate["family"]}
    prepared = prepare_candidate(bars, base)
    if candidate["family"] == "rejection":
        high = (bars.bid_high + bars.ask_high) / 2
        low = (bars.bid_low + bars.ask_low) / 2
        close = (bars.bid_close + bars.ask_close) / 2
        upper = high.shift(1).rolling(candidate["period"]).max()
        lower = low.shift(1).rolling(candidate["period"]).min()
        sell = high.gt(upper) & close.lt(upper)
        buy = low.lt(lower) & close.gt(lower)
        prepared["signal"] = np.select([buy & ~sell, sell & ~buy], [1, -1], default=0).astype(np.int8)
    if "risk_share" in candidate:
        prepared = apply_risk_budget(prepared, stop_atr=candidate["stop_atr"], account_usd=20.,
                                     risk_share=candidate["risk_share"], usd_per_price_unit=.01)
    return prepared
