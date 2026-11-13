import numpy as np
import pandas as pd
import pytest

from goldnix_research.candidates import prepare_candidate


def bars(close):
    close = np.asarray(close, dtype=float)
    return pd.DataFrame({
        "timestamp_utc": pd.date_range("2020-01-06", periods=len(close), freq="h", tz="UTC"),
        "bid_open": close, "bid_high": close + .2, "bid_low": close - .2, "bid_close": close,
        "ask_open": close + .1, "ask_high": close + .3, "ask_low": close - .1, "ask_close": close + .1,
        "provider_volume": 1., "era": "TEST",
    })


@pytest.mark.parametrize("direction", [1, -1])
def test_pullback_waits_for_fast_rsi_recovery_in_slow_trend(direction):
    close = np.array([100, 102, 104, 106, 108, 110, 109, 108, 109])
    if direction == -1:
        close = 200 - close
    result = prepare_candidate(bars(close), {"family": "pullback", "slow_period": 5, "rsi_cut": 50})
    assert result.signal.tolist() == [0] * 8 + [direction]
    assert bool(result.iloc[-1]["buy_eligible" if direction == 1 else "sell_eligible"])


def test_channel_compares_closed_price_with_prior_range_without_current_high():
    result = prepare_candidate(bars([100, 101, 102, 104, 99]), {"family": "channel", "period": 3})
    assert result.signal.tolist() == [0, 0, 0, 1, -1]


def test_aroon_control_preserves_existing_index_and_tie_contract():
    frame = bars([102.5, 104, 103, 105, 107])
    frame["bid_high"] = [103, 105, 104, 106, 108]
    frame["bid_low"] = [102, 101, 102, 103, 100]
    frame["ask_high"], frame["ask_low"] = frame.bid_high + .1, frame.bid_low + .1
    result = prepare_candidate(frame, {"family": "aroon", "period": 3, "threshold": 50})
    assert result.signal.tolist() == [0, 0, 0, 1, 0]


@pytest.mark.parametrize("candidate", [
    {"family": "aroon", "period": 7, "threshold": 50},
    {"family": "pullback", "slow_period": 20, "rsi_cut": 20},
    {"family": "channel", "period": 10},
])
def test_future_prices_cannot_change_past_signals_or_eligibility(candidate):
    frame = bars(100 + np.sin(np.arange(100) / 3) * 10)
    original = prepare_candidate(frame.iloc[:70], candidate)
    changed = frame.copy()
    for column in [c for c in changed if c.startswith(("bid_", "ask_"))]:
        changed.loc[70:, column] *= 10
    extended = prepare_candidate(changed, candidate)
    columns = ["signal", "atr", "buy_eligible", "sell_eligible"]
    pd.testing.assert_frame_equal(original[columns], extended.iloc[:70][columns])
