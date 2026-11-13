import numpy as np
import pandas as pd

from goldnix_h02.method import FakeoutMarket
from goldnix_h02.tests.test_context import bars


def path():
    data = bars(7)
    for kind, values in {
        "open": [100, 100, 99.9, 99.8, 99.5, 100, 106],
        "high": [100.4, 100.3, 100.1, 100, 100, 106.5, 106.4],
        "low": [99.9, 99.8, 99.6, 99.5, 99.4, 99.8, 105.8],
        "close": [100.1, 100, 99.7, 99.6, 99.9, 106, 106.2],
    }.items():
        data[f"bid_{kind}"] = values
        data[f"ask_{kind}"] = np.asarray(values) + .2
    return data


def trade(data, **kwargs):
    market = FakeoutMarket(data, {"atr": np.ones(len(data)), "ready": np.ones(len(data), bool)},
                           {"usd_per_price_unit": .01})
    return market.trade(0, 1, 2., {"reward_r": 3., "max_hold_minutes": 10**9}, "fixture", len(data)-1,
                        fakeout=True, level=100., buffer=.1, **kwargs)


def test_fakeout_needs_closed_m15_then_next_m5_and_exits_at_following_open():
    result = trade(path())
    assert result["exit_reason"] == "fakeout_confirmed"
    assert result["exit_index"] == 4
    assert result["exit"] == 99.5
    assert result["stop"] == 98.
    assert result["target"] == 106.
    assert result["warning_index"] == 2 and result["confirmation_index"] == 3


def test_reclaim_or_missing_confirmation_cancels_warning():
    data = path()
    for side, spread in [("bid", 0), ("ask", .2)]:
        data.loc[3, f"{side}_close"] = 100.3 + spread
        data.loc[3, f"{side}_high"] = 100.5 + spread
    assert trade(data)["exit_reason"] == "target"
    assert trade(path().drop(index=3).reset_index(drop=True))["exit_reason"] == "target"


def test_stop_during_confirmation_precedes_discretionary_exit():
    data = path()
    data.loc[3, "bid_low"] = 97.9
    data.loc[3, "ask_low"] = 98.1
    result = trade(data)
    assert result["exit_reason"] == "stop" and result["exit_index"] == 3


def test_confirmed_intent_survives_missing_next_quote_and_uses_actual_open():
    data = path()
    data.loc[4:, "epoch_seconds"] += 300
    data["timestamp_utc"] = pd.to_datetime(data.epoch_seconds, unit="s", utc=True)
    result = trade(data)
    assert result["exit_reason"] == "fakeout_confirmed"
    assert result["exit"] == 99.5 and result["flags"] == "gap_risk"
    assert result["exit_ts"] == data.timestamp_utc.iloc[4]


def test_adverse_open_gap_keeps_server_stop_priority():
    data = path()
    for side, spread in [("bid", 0), ("ask", .2)]:
        for kind, value in [("open", 97), ("high", 98), ("low", 96.8), ("close", 97.5)]:
            data.loc[4, f"{side}_{kind}"] = value + spread
    result = trade(data)
    assert result["exit_reason"] == "gap_stop" and result["exit"] == 97


def test_planned_exit_at_open_precedes_later_intrabar_stop_and_future_does_not_matter():
    data = path()
    data.loc[4, "bid_low"], data.loc[4, "ask_low"] = 97.8, 98.
    full = trade(data)
    prefix = trade(data.iloc[:5])
    for result in (full, prefix):
        assert result["exit_reason"] == "fakeout_confirmed"
        assert result["exit_index"] == 4 and result["exit"] == 99.5


def test_sell_failure_uses_ask_and_mirrors_buy():
    data, mirrored = path(), path()
    for side, other in [("bid", "ask"), ("ask", "bid")]:
        for kind, inverse in [("open", "open"), ("high", "low"), ("low", "high"), ("close", "close")]:
            mirrored[f"{side}_{kind}"] = 300 - data[f"{other}_{inverse}"]
    market = FakeoutMarket(mirrored, {"atr": np.ones(len(data)), "ready": np.ones(len(data), bool)},
                           {"usd_per_price_unit": .01})
    result = market.trade(0, -1, 2., {"reward_r": 3., "max_hold_minutes": 10**9}, "fixture", len(data)-1,
                          fakeout=True, level=200., buffer=.1)
    assert result["exit_index"] == 4 and result["exit"] == 200.5
    assert np.isclose(result["pnl_usd"], trade(data)["pnl_usd"])
