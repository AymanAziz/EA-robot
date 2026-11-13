"""Behavioral checks for causal signals, quote sides, and loss controls."""

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from goldnix_mtf.data import validate
from goldnix_mtf.method import (aggregate, available_rows, confirm, ema, features,
                                outcome_pool, select_schedule, signals)


@pytest.fixture
def protocol():
    return json.loads((Path(__file__).parents[1] / "protocol.json").read_text())


def bars(values, start="2024-02-05T00:00:00Z", spread=.2):
    values = np.asarray(values, float)
    ts = pd.date_range(start, periods=len(values), freq="5min")
    frame = pd.DataFrame({"timestamp_utc": ts, "epoch_seconds": ts.asi8 // 10**9,
                          "provider_volume": 10.})
    for side, offset in (("bid", 0.), ("ask", spread)):
        for kind, change in (("open", 0.), ("high", .1), ("low", -.1), ("close", 0.)):
            frame[f"{side}_{kind}"] = values + offset + change
    return frame


def test_only_completed_h1_is_available():
    raw = bars(np.arange(36) + 100, "2024-02-05T09:00:00Z")
    higher = aggregate(raw, 60)
    indices = available_rows(pd.to_datetime(["2024-02-05T09:55Z", "2024-02-05T10:35Z",
                                             "2024-02-05T11:00Z"]), higher)
    assert indices.tolist() == [-1, 0, 1]
    assert higher.iloc[indices[1]].bid_close == 111


def test_incomplete_aggregate_is_not_fabricated():
    raw = bars(np.arange(24) + 100).drop(index=5)
    assert len(aggregate(raw, 60)) == 1
    assert len(aggregate(raw, 15)) == 7


def test_ema_has_explicit_sma_seed():
    result = ema([1, 3, 5, 9], 3)
    assert np.isnan(result[:2]).all()
    assert result[2:].tolist() == [3., 6.]


@pytest.mark.parametrize("direction", [1, -1])
def test_break_retest_reclaim_is_symmetric(direction):
    raw = bars([100, 100.5, 100.6])
    raw.loc[2, "bid_low"] = 100.1
    if direction == -1:
        high, low = raw.bid_high.copy(), raw.bid_low.copy()
        raw["bid_close"] = 200 - raw.bid_close
        raw["bid_high"], raw["bid_low"] = 200 - low, 200 - high
    assert confirm(raw, 0, direction, 100, .2, 1., 1.) == "confirmed"


@pytest.mark.parametrize("change,reason", [
    ((1, "bid_close", 100.1), "no_closing_break"),
    ((2, "bid_low", 99.7), "no_bounded_retest"),
    ((2, "bid_close", 100.1), "no_reclaim"),
    ((2, "bid_close", 101.1), "extended_reclaim")])
def test_wicks_deep_failures_and_chasing_are_rejected(change, reason):
    raw = bars([100, 100.5, 100.6])
    raw.loc[2, "bid_low"] = 100.1
    raw.loc[change[0], change[1]] = change[2]
    assert confirm(raw, 0, 1, 100, .2, 1., 1.) == reason


def test_missing_confirmation_candle_rejects():
    raw = bars([100, 100.5, 100.6, 100.7]).drop(index=1).reset_index(drop=True)
    assert confirm(raw, 0, 1, 100, .2, 1., 1.) == "missing_confirmation_bar"


def test_future_prices_cannot_change_past_features_or_signals(protocol):
    # Short warmup is a synthetic test fixture, never a historical strategy variant.
    protocol["signals"].update(warmup_bars_per_timeframe=8, h1_ema_period=5, m15_ema_period=5)
    values = 100 + np.arange(1200) * .005 + np.sin(np.arange(1200) / 9)
    raw = bars(values)
    cutoff = 900
    prefix = raw.iloc[:cutoff].copy()
    first = features(prefix, protocol)
    changed = raw.copy()
    for column in [c for c in raw if c.startswith(("bid_", "ask_"))]:
        changed.loc[cutoff:, column] += 1000
    after = features(changed, protocol)
    for key in ("atr", "ready", "h1_direction", "h1_available_at"):
        np.testing.assert_allclose(first[key], after[key][:cutoff], equal_nan=True)
    a, _ = signals(prefix, first, protocol)
    b, _ = signals(changed, after, protocol)
    np.testing.assert_array_equal(a[:cutoff - 3], b[:cutoff - 3])


def pool_fixture(raw, protocol):
    ready = {"ready": np.ones(len(raw), bool), "atr": np.ones(len(raw))}
    return outcome_pool(raw, ready, protocol, "TEST", ["2024-02-05T00:00Z", "2024-02-06T00:00Z"])


def test_buy_and_sell_pay_spread_at_correct_sides(protocol):
    raw = bars([100, 100, 100.5, 100.6])
    pool = pool_fixture(raw, protocol)
    pair = pool.loc[pool.entry_index.eq(1)].set_index("dir")
    assert pair.loc["BUY", "entry"] == 100.2
    assert pair.loc["BUY", "exit"] == 100.5
    assert pair.loc["SELL", "entry"] == 100
    assert pair.loc["SELL", "exit"] == 100.7
    assert pair.loc["BUY", "r_multiple"] == pytest.approx(.3)
    assert pair.loc["SELL", "r_multiple"] == pytest.approx(-.7)
    assert pair.loc["BUY", "pnl_usd"] == pytest.approx(.003)


def test_stop_precedes_timed_exit_and_includes_spread(protocol):
    raw = bars([100, 100, 103, 103])
    raw.loc[1, "bid_low"] = 98.5
    buy = pool_fixture(raw, protocol).query("entry_index == 1 and dir == 'BUY'").iloc[0]
    assert buy.exit == 99
    assert buy.r_multiple == pytest.approx(-1.2)
    assert buy.exit_reason == "stop"


def test_sell_stop_uses_ask_extreme(protocol):
    raw = bars([100, 100, 99, 99])
    raw.loc[1, "ask_high"] = 101.3
    sell = pool_fixture(raw, protocol).query("entry_index == 1 and dir == 'SELL'").iloc[0]
    assert sell.stop == pytest.approx(101.2)
    assert sell.r_multiple == pytest.approx(-1.2)


def test_missing_exit_does_not_delete_losing_trade(protocol):
    raw = bars([100, 100, 100, 95, 96]).drop(index=2).reset_index(drop=True)
    buy = pool_fixture(raw, protocol).query("entry_index == 1 and dir == 'BUY'").iloc[0]
    assert buy.exit == 95
    assert buy["flags"] == "gap_risk"
    assert buy.r_multiple == pytest.approx(-5.2)


def test_daily_halt_and_position_lockout(protocol):
    raw = bars(np.full(12, 100.))
    raw["bid_low"] = 98.5
    pool = pool_fixture(raw, protocol)
    signal = np.ones(len(raw), dtype=int)
    selected, _ = select_schedule(pool, signal, -2)
    assert selected.entry_index.tolist() == [1, 3]
    assert selected.r_multiple.sum() == pytest.approx(-2.4)


def test_spread_and_era_boundary_are_enforced(protocol):
    raw = bars([100, 100, 100, 100], spread=3)
    assert pool_fixture(raw, protocol).empty
    raw = bars([100, 100, 100], "2024-02-05T23:50:00Z")
    assert pool_fixture(raw, protocol).empty


def test_bad_quotes_are_quarantined_and_duplicate_times_abort():
    raw = bars([100, 100, 100])
    raw.loc[1, "ask_open"] = 99
    good, bad = validate(raw, 2024)
    assert len(good) == 2 and len(bad) == 1
    raw.loc[2, "epoch_seconds"] = raw.epoch_seconds.iloc[1]
    with pytest.raises(ValueError, match="Duplicate"):
        validate(raw, 2024)


@pytest.mark.parametrize("direction", [1, -1])
def test_complete_setup_emits_once_after_reclaim(protocol, direction):
    protocol["signals"]["warmup_bars_per_timeframe"] = 1
    raw = bars([99, 99, 99.8, 100.5, 100.6, 100.6, 101])
    raw.loc[4, "bid_low"] = 100.1
    setup = {"bid_high": 100., "bid_low": 99., "bid_close": 99.8, "ema": 99.5}
    if direction == -1:
        high, low = raw.bid_high.copy(), raw.bid_low.copy()
        raw["bid_open"], raw["bid_close"] = 200 - raw.bid_open, 200 - raw.bid_close
        raw["bid_high"], raw["bid_low"] = 200 - low, 200 - high
        for kind in ("open", "high", "low", "close"):
            raw[f"ask_{kind}"] = raw[f"bid_{kind}"] + .2
        setup = {"bid_high": 101., "bid_low": 100., "bid_close": 100.2, "ema": 100.5}
    higher = pd.DataFrame({"available_at": pd.to_datetime(["2024-02-05T00:00Z"]),
                          "direction": direction, "bid_close": 99., "ema": 98.})
    middle = pd.DataFrame([{**setup, "available_at": pd.Timestamp("2024-02-05T00:15Z")}])
    prepared = {"h1": higher, "m15": middle, "ready": np.ones(len(raw), bool),
                "atr": np.ones(len(raw)), "h1_direction": np.full(len(raw), direction)}
    emitted, audit = signals(raw, prepared, protocol)
    assert np.flatnonzero(emitted).tolist() == [4]
    assert emitted[4] == direction
    assert audit.reason.tolist() == ["confirmed"]
    assert audit.entry_index.tolist() == [5]


def test_intrabar_stop_is_realized_before_midnight(protocol):
    raw = bars(np.full(8, 100.), "2024-02-05T23:50Z")
    raw.loc[1, "bid_low"] = 98.5
    prepared = {"ready": np.ones(len(raw), bool), "atr": np.ones(len(raw))}
    pool = outcome_pool(raw, prepared, protocol, "TEST", ["2024-02-05T00:00Z", "2024-02-07T00:00Z"])
    stop = pool.query("entry_index == 1 and dir == 'BUY'").iloc[0]
    assert stop.exit_day == stop.entry_day
    assert stop.exit_ts == pd.Timestamp("2024-02-05T23:55Z")
    assert stop.exit_time_precision == "M5_bar_open_label"
    assert stop.exit_not_after_exclusive == pd.Timestamp("2024-02-06T00:00Z")
    # The conservative position slot is unchanged despite the timestamp label.
    assert stop.exit_index == 2
