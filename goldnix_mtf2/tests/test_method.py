import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from goldnix_mtf2.method import Market, confirmation_signals


@pytest.fixture
def protocol():
    return json.loads((Path(__file__).parents[1] / "protocol.json").read_text())


def make_bars(values, start="2024-02-05T10:00Z", spread=.1):
    values = np.asarray(values, dtype=float)
    times = pd.date_range(start, periods=len(values), freq="5min")
    frame = pd.DataFrame({"timestamp_utc": times, "epoch_seconds": times.asi8 // 10**9})
    for side, offset in (("bid", 0), ("ask", spread)):
        for kind, change in (("open", 0), ("high", .1), ("low", -.1), ("close", 0)):
            frame[f"{side}_{kind}"] = values + offset + change
    return frame


def market(frame, protocol):
    return Market(frame, {"atr": np.ones(len(frame)), "ready": np.ones(len(frame), bool)}, protocol)


def config(reward=2, hold=15):
    return {"stop_atr": 1., "reward_r": reward, "max_hold_minutes": hold}


@pytest.mark.parametrize("d", [1, -1])
def test_stop_uses_correct_side_and_pays_spread(protocol, d):
    frame = make_bars([100] * 5)
    frame.loc[1, "bid_low"] = 98.5
    frame.loc[1, "ask_high"] = 101.5
    m = market(frame, protocol)
    trade = m.trade(1, d, 1., config(), "TEST", 4)
    assert trade["r_multiple"] == pytest.approx(-1.1)
    assert trade["pnl_usd"] == pytest.approx(-.011)
    assert trade["exit_reason"] == "stop"


def test_both_hit_bar_has_conservative_primary_and_sensitivity(protocol):
    frame = make_bars([100] * 5)
    frame.loc[1, ["bid_low", "bid_high"]] = [98, 103]
    m = market(frame, protocol)
    conservative = m.trade(1, 1, 1., config(), "TEST", 4)
    optimistic = m.trade(1, 1, 1., config(), "TEST", 4, "target_first")
    assert conservative["r_multiple"] == pytest.approx(-1.1)
    assert optimistic["r_multiple"] == pytest.approx(1.9)
    assert conservative["ambiguous_exit_bar"]


def test_missing_quote_retains_adverse_gap_at_actual_price(protocol):
    frame = make_bars([100, 100, 100, 95, 95]).drop(index=2).reset_index(drop=True)
    m = market(frame, protocol)
    trade = m.trade(1, 1, 1., config(), "TEST", 3)
    assert trade["exit"] == 95
    assert trade["r_multiple"] == pytest.approx(-5.1)
    assert trade["flags"] == "gap_risk"
    assert trade["exit_reason"] == "gap_stop"


def test_timed_exit_uses_elapsed_clock_and_first_available_quote(protocol):
    frame = make_bars([100, 100, 100, 100, 100, 98]).drop(index=[2, 3, 4]).reset_index(drop=True)
    m = market(frame, protocol)
    trade = m.trade(1, 1, 1., config(hold=5), "TEST", 2)
    assert trade["exit_reason"] == "time_exit"
    assert trade["exit"] == 98
    assert trade["flags"] == "gap_risk"


def test_era_boundary_closes_position_without_reading_later_prices(protocol):
    frame = make_bars([100, 100, 100.5, 200, 200])
    trade = market(frame, protocol).trade(1, 1, 1., config(hold=180), "TEST", 2)
    assert trade["exit"] == 100.5
    assert trade["exit_reason"] == "era_end"


def test_cash_risk_includes_spread_and_rejects_minimum_lot_trade(protocol):
    frame = make_bars([100] * 5, spread=.2)
    m = market(frame, protocol)
    allowed, _ = m.eligible([1], 1, {**config(), "stop_atr": 2.9})
    assert not allowed[0]  # 2.9 + .2 costs 3.1 USC, exceeding the fixed 3 USC cap.
    allowed, _ = m.eligible([1], 1, config())
    assert allowed[0]


def test_overnight_stop_is_booked_to_its_candle_day(protocol):
    frame = make_bars([100] * 5, "2024-02-05T23:50Z")
    frame.loc[1, "bid_low"] = 98
    trade = market(frame, protocol).trade(1, 1, 1., config(), "TEST", 4)
    assert trade["entry_day"] == trade["exit_day"]


def setup_fixture():
    frame = make_bars([99, 99, 99.8, 100.8, 100.6, 100.5, 100.6, 100.6, 100.7], spread=.2)
    frame.loc[6, "bid_low"] = 100.1
    middle = pd.DataFrame({"available_at": pd.date_range(end="2024-02-05T10:15Z", periods=500, freq="15min"),
                          "bid_low": 99., "bid_high": 100., "bid_close": 99.8, "ema": 99.5})
    higher = pd.DataFrame({"available_at": pd.to_datetime(["2024-02-05T10:00Z"]), "direction": [1]})
    prepared = {"m15": middle, "h1": higher, "ready": np.ones(len(frame), bool),
                "atr": np.ones(len(frame)), "h1_direction": np.ones(len(frame), int)}
    return frame, prepared


def test_retest_can_arrive_later_within_fixed_window(protocol):
    frame, prepared = setup_fixture()
    signal, audit = confirmation_signals(frame, prepared, "retest", protocol)
    assert np.flatnonzero(signal).tolist() == [6]
    assert audit.reason.tolist() == ["confirmed"]


def test_hold_confirms_without_retest_touch(protocol):
    frame, prepared = setup_fixture()
    signal, _ = confirmation_signals(frame, prepared, "hold", protocol)
    assert np.flatnonzero(signal).tolist() == [4]


def test_setup_invalidation_cancels_future_reclaim(protocol):
    frame, prepared = setup_fixture()
    frame.loc[4, "bid_low"] = 98
    signal, audit = confirmation_signals(frame, prepared, "retest", protocol)
    assert not signal.any()
    assert audit.reason.tolist() == ["setup_invalidated"]


def test_expired_setup_never_uses_later_confirmation(protocol):
    frame, prepared = setup_fixture()
    frame.loc[6, "bid_low"] = 100.5
    frame.loc[7, "bid_low"] = 100.5
    frame.loc[8, "bid_low"] = 100.6
    signal, audit = confirmation_signals(frame, prepared, "retest", protocol)
    assert not signal.any()
    assert audit.reason.tolist() == ["expired_without_confirmation"]


def test_simulation_applies_daily_halt_and_no_overlapping_positions(protocol):
    frame = make_bars(100 - .5 * np.arange(15))
    frame["bid_low"] = frame.bid_open - 1.2
    m = market(frame, protocol)
    signal = np.ones(len(frame), int)
    trades = m.simulate(signal, config(), "TEST", ["2024-02-05T00:00Z", "2024-02-06T00:00Z"])
    assert len(trades) <= 2
    assert trades.entry_index.is_unique
    assert trades.r_multiple.sum() <= -2


def test_sell_retest_uses_mirrored_price_structure(protocol):
    frame, prepared = setup_fixture()
    high, low = frame.bid_high.copy(), frame.bid_low.copy()
    frame["bid_open"], frame["bid_close"] = 200 - frame.bid_open, 200 - frame.bid_close
    frame["bid_high"], frame["bid_low"] = 200 - low, 200 - high
    for kind in ("open", "high", "low", "close"):
        frame[f"ask_{kind}"] = frame[f"bid_{kind}"] + .2
    prepared["m15"]["bid_high"] = 101.
    prepared["m15"]["bid_low"] = 100.
    prepared["m15"]["bid_close"] = 100.2
    prepared["m15"]["ema"] = 100.5
    prepared["h1"]["direction"] = -1
    prepared["h1_direction"] *= -1
    signal, _ = confirmation_signals(frame, prepared, "retest", protocol)
    assert np.flatnonzero(signal).tolist() == [6]
    assert signal[6] == -1


def test_future_prices_do_not_change_confirmed_entry(protocol):
    frame, prepared = setup_fixture()
    a, _ = confirmation_signals(frame, prepared, "hold", protocol)
    for column in [c for c in frame if c.startswith(("bid_", "ask_"))]:
        frame.loc[6:, column] += 100
    b, _ = confirmation_signals(frame, prepared, "hold", protocol)
    np.testing.assert_array_equal(a[:5], b[:5])
