from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from params.config import load_yaml
from sim.engine import run_engine
from ingest.gaps import find_gaps
from goldnix_round2.execution import run_managed


def config(**changes):
    original = load_yaml(Path(__file__).resolve().parents[2] / "goldnix/params/decision.yaml")
    return {**original, "exit_management": "fixed", **changes}


def frame(close, *, signals=None):
    values = np.asarray(close, dtype=float)
    return pd.DataFrame({
        "timestamp_utc": pd.date_range("2025-01-06", periods=len(values), freq="h", tz="UTC"),
        "bid_open": values, "bid_high": values + .5, "bid_low": values - .5, "bid_close": values,
        "ask_open": values + .2, "ask_high": values + .7, "ask_low": values - .3,
        "ask_close": values + .2, "atr": 1., "signal": signals if signals is not None else 1,
        "era": "TEST",
    })


def test_fixed_mode_matches_pinned_engine_including_daily_halts_friday_and_gaps():
    rng = np.random.default_rng(19)
    bars = frame(100 + rng.normal(size=600).cumsum(), signals=rng.choice([-1, 0, 1], size=600))
    bars = bars.drop(index=range(50, 60)).reset_index(drop=True)
    gaps = find_gaps(bars)
    expected = run_engine(bars, config(), gaps=gaps).trades
    actual = run_managed(bars, config(), gaps=gaps)
    pd.testing.assert_frame_equal(actual, expected, check_dtype=False, rtol=1e-12, atol=1e-12)


def test_break_even_is_applied_next_bar_and_a_gap_can_still_lose_money():
    bars = frame([100, 100, 100], signals=[1, 0, 0])
    bars.loc[1, ["bid_high", "bid_low", "bid_close"]] = [101.5, 99.5, 101.3]
    bars.loc[1, ["ask_high", "ask_low", "ask_close"]] = [101.7, 99.7, 101.5]
    trade = run_managed(bars, config(exit_management="break_even", target_atr=3)).iloc[0]
    assert trade.exit_ts == bars.timestamp_utc.iloc[2]
    assert trade.exit == pytest.approx(100)
    assert trade.r_multiple == pytest.approx(-.2)
    assert trade.exit_reason == "gap_stop"


@pytest.mark.parametrize("mode", ["break_even", "trail"])
def test_intrabar_high_does_not_activate_protection_when_close_did_not(mode):
    bars = frame([100, 100, 100], signals=[1, 0, 0])
    bars.loc[1, ["bid_high", "bid_low", "bid_close"]] = [102.5, 99.5, 100.5]
    bars.loc[1, ["ask_high", "ask_low", "ask_close"]] = [102.7, 99.7, 100.7]
    bars.loc[2, "bid_low"] = 98.9
    trade = run_managed(bars, config(exit_management=mode, target_atr=3)).iloc[0]
    assert trade.r_multiple == pytest.approx(-1.2)
    assert trade.exit_reason == "stop"


@pytest.mark.parametrize("mode", ["break_even", "trail"])
def test_short_protection_uses_ask_quote_and_next_bar_only(mode):
    bars = frame([100, 100, 100], signals=[-1, 0, 0])
    bars.loc[1, ["ask_high", "ask_low", "ask_close"]] = [100.7, 97.6, 97.8]
    bars.loc[1, ["bid_high", "bid_low", "bid_close"]] = [100.5, 97.4, 97.6]
    trade = run_managed(bars, config(exit_management=mode, target_atr=3)).iloc[0]
    assert trade.exit == pytest.approx(100.2)
    assert trade.r_multiple == pytest.approx(-.2)
    assert trade.exit_reason == "gap_stop"


def test_trailing_stop_uses_previous_close_and_preserves_gap_fill():
    bars = frame([100, 100, 101], signals=[1, 0, 0])
    bars.loc[1, ["bid_high", "bid_low", "bid_close"]] = [102.6, 99.5, 102.5]
    bars.loc[1, ["ask_high", "ask_low", "ask_close"]] = [102.8, 99.7, 102.7]
    trade = run_managed(bars, config(exit_management="trail", target_atr=3)).iloc[0]
    assert trade.exit == pytest.approx(101)
    assert trade.r_multiple == pytest.approx(.8)
    assert trade.exit_reason == "gap_stop"
