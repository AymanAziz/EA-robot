"""Hand-computed behaviour tests for the H1 simulation engine."""

from __future__ import annotations

import pandas as pd
import pytest

from sim.engine import prepare_bars, run_engine


def _config(**overrides):
    config = {
        "vol_ceiling_atr": 0.30,
        "stop_atr": 1.0,
        "target_atr": 2.0,
        "min_distance_usd": 0.50,
        "friday_no_entry_from_utc": "19:00",
        "friday_flat_utc": "20:00",
        "daily_halt_r": -2.0,
        "holiday_exclusion": True,
        "fill_policy": "stop_first",
        "gap_policy": "adverse_at_open_favourable_at_target",
    }
    config.update(overrides)
    return config


def _bars(rows):
    defaults = {
        "era": "D",
        "signal": 0,
        "atr": 1.0,
        "bid_open": 100.0,
        "bid_high": 100.5,
        "bid_low": 99.5,
        "bid_close": 100.0,
        "ask_open": 100.4,
        "ask_high": 100.9,
        "ask_low": 99.9,
        "ask_close": 100.2,
    }
    materialized = [{**defaults, **row} for row in rows]
    frame = pd.DataFrame(materialized)
    frame["timestamp_utc"] = pd.to_datetime(frame.pop("timestamp_utc"), utc=True)
    return frame


def test_long_target_charges_one_entry_spread_and_reports_r():
    bars = _bars(
        [
            {"timestamp_utc": "2025-01-06T00:00:00Z", "signal": 1},
            {"timestamp_utc": "2025-01-06T01:00:00Z"},
            {
                "timestamp_utc": "2025-01-06T02:00:00Z",
                "bid_high": 102.2,
                "bid_low": 100.0,
                "bid_close": 102.0,
                "ask_high": 102.6,
                "ask_low": 100.4,
                "ask_close": 102.4,
            },
        ]
    )

    result = run_engine(bars, _config())

    assert len(result.trades) == 1
    trade = result.trades.iloc[0]
    assert trade["dir"] == "BUY"
    assert trade["entry"] == pytest.approx(100.4)
    assert trade["stop"] == pytest.approx(99.0)
    assert trade["target"] == pytest.approx(102.0)
    assert trade["exit"] == pytest.approx(102.0)
    assert trade["spread_paid"] == pytest.approx(0.4)
    assert trade["r_multiple"] == pytest.approx(1.6)
    assert trade["mae_r"] == pytest.approx(-0.9)
    assert trade["mfe_r"] == pytest.approx(1.8)
    assert trade["exit_reason"] == "target"


def test_long_stop_charges_one_entry_spread_and_reports_r():
    bars = _bars(
        [
            {"timestamp_utc": "2025-01-06T00:00:00Z", "signal": 1},
            {"timestamp_utc": "2025-01-06T01:00:00Z"},
            {
                "timestamp_utc": "2025-01-06T02:00:00Z",
                "bid_high": 100.5,
                "bid_low": 98.8,
                "bid_close": 99.0,
                "ask_high": 100.9,
                "ask_low": 99.2,
                "ask_close": 99.4,
            },
        ]
    )

    result = run_engine(bars, _config())

    trade = result.trades.iloc[0]
    assert trade["exit"] == pytest.approx(99.0)
    assert trade["r_multiple"] == pytest.approx(-1.4)
    assert trade["exit_reason"] == "stop"


@pytest.mark.parametrize(
    ("fill_policy", "expected_exit", "expected_reason"),
    [
        ("stop_first", 99.0, "stop"),
        ("target_first", 102.0, "target"),
    ],
)
def test_same_bar_touch_obeys_declared_fill_policy(
    fill_policy, expected_exit, expected_reason
):
    bars = _bars(
        [
            {"timestamp_utc": "2025-01-06T00:00:00Z", "signal": 1},
            {
                "timestamp_utc": "2025-01-06T01:00:00Z",
                "bid_high": 102.2,
                "bid_low": 98.8,
            },
        ]
    )

    result = run_engine(bars, _config(fill_policy=fill_policy))

    assert result.trades.iloc[0]["exit"] == pytest.approx(expected_exit)
    assert result.trades.iloc[0]["exit_reason"] == expected_reason


def test_adverse_gap_through_long_stop_fills_at_bid_open():
    bars = _bars(
        [
            {"timestamp_utc": "2025-01-06T00:00:00Z", "signal": 1},
            {"timestamp_utc": "2025-01-06T01:00:00Z"},
            {
                "timestamp_utc": "2025-01-06T08:00:00Z",
                "bid_open": 98.5,
                "bid_high": 99.0,
                "bid_low": 98.0,
                "ask_open": 98.9,
                "ask_high": 99.4,
                "ask_low": 98.4,
            },
        ]
    )

    trade = run_engine(bars, _config()).trades.iloc[0]

    assert trade["exit"] == pytest.approx(98.5)
    assert trade["r_multiple"] == pytest.approx(-1.9)
    assert trade["exit_reason"] == "gap_stop"


def test_favourable_gap_through_long_target_fills_at_target():
    bars = _bars(
        [
            {"timestamp_utc": "2025-01-06T00:00:00Z", "signal": 1},
            {"timestamp_utc": "2025-01-06T01:00:00Z"},
            {
                "timestamp_utc": "2025-01-06T08:00:00Z",
                "bid_open": 102.5,
                "bid_high": 103.0,
                "bid_low": 102.2,
                "ask_open": 102.9,
                "ask_high": 103.4,
                "ask_low": 102.6,
            },
        ]
    )

    trade = run_engine(bars, _config()).trades.iloc[0]

    assert trade["exit"] == pytest.approx(102.0)
    assert trade["r_multiple"] == pytest.approx(1.6)
    assert trade["exit_reason"] == "gap_target"


def test_friday_flat_closes_long_at_bid_open_before_intrabar_checks():
    bars = _bars(
        [
            {"timestamp_utc": "2025-01-10T17:00:00Z", "signal": 1},
            {"timestamp_utc": "2025-01-10T18:00:00Z"},
            {"timestamp_utc": "2025-01-10T19:00:00Z"},
            {
                "timestamp_utc": "2025-01-10T20:00:00Z",
                "bid_open": 100.2,
                "bid_high": 102.5,
                "bid_low": 98.5,
                "ask_open": 100.6,
                "ask_high": 102.9,
                "ask_low": 98.9,
            },
        ]
    )

    trade = run_engine(bars, _config()).trades.iloc[0]

    assert trade["exit"] == pytest.approx(100.2)
    assert trade["r_multiple"] == pytest.approx(-0.2)
    assert trade["exit_reason"] == "friday_flat"


def test_holiday_signal_is_skipped_but_bar_remains_available():
    bars = _bars(
        [
            {"timestamp_utc": "2025-12-25T00:00:00Z", "signal": 1},
            {
                "timestamp_utc": "2025-12-25T01:00:00Z",
                "bid_high": 103.0,
            },
        ]
    )

    result = run_engine(bars, _config())

    assert result.signals == 1
    assert result.trades.empty


def test_vol_ceiling_uses_signal_close_spread_and_counts_the_skip():
    bars = _bars(
        [
            {
                "timestamp_utc": "2025-01-06T00:00:00Z",
                "signal": 1,
                "bid_close": 100.0,
                "ask_close": 100.31,
            },
            {
                "timestamp_utc": "2025-01-06T01:00:00Z",
                "bid_high": 103.0,
            },
        ]
    )

    result = run_engine(bars, _config())

    assert result.signals == 1
    assert result.skipped_by_vol_ceiling == 1
    assert result.trades.empty


def test_short_target_uses_ask_side_and_charges_one_entry_spread():
    bars = _bars(
        [
            {"timestamp_utc": "2025-01-06T00:00:00Z", "signal": -1},
            {"timestamp_utc": "2025-01-06T01:00:00Z"},
            {
                "timestamp_utc": "2025-01-06T02:00:00Z",
                "bid_high": 99.0,
                "bid_low": 97.8,
                "ask_open": 99.4,
                "ask_high": 99.4,
                "ask_low": 98.2,
                "ask_close": 98.4,
            },
        ]
    )

    trade = run_engine(bars, _config()).trades.iloc[0]

    assert trade["dir"] == "SELL"
    assert trade["entry"] == pytest.approx(100.0)
    assert trade["stop"] == pytest.approx(101.4)
    assert trade["target"] == pytest.approx(98.4)
    assert trade["exit"] == pytest.approx(98.4)
    assert trade["spread_paid"] == pytest.approx(0.4)
    assert trade["r_multiple"] == pytest.approx(1.6)
    assert trade["exit_reason"] == "target"


def test_opposite_signal_is_ignored_while_position_is_open():
    bars = _bars(
        [
            {"timestamp_utc": "2025-01-06T00:00:00Z", "signal": 1},
            {"timestamp_utc": "2025-01-06T01:00:00Z", "signal": -1},
            {"timestamp_utc": "2025-01-06T02:00:00Z"},
            {
                "timestamp_utc": "2025-01-06T03:00:00Z",
                "bid_high": 102.2,
                "bid_low": 100.0,
            },
        ]
    )

    result = run_engine(bars, _config())

    assert result.signals == 2
    assert len(result.trades) == 1
    assert result.trades.iloc[0]["dir"] == "BUY"


def test_daily_halt_blocks_new_entries_after_realised_r_reaches_limit():
    bars = _bars(
        [
            {"timestamp_utc": "2025-01-06T00:00:00Z", "signal": 1},
            {
                "timestamp_utc": "2025-01-06T01:00:00Z",
                "signal": 1,
                "bid_low": 98.8,
            },
            {
                "timestamp_utc": "2025-01-06T02:00:00Z",
                "signal": 1,
                "bid_low": 98.8,
                "ask_close": 100.5,
            },
            {
                "timestamp_utc": "2025-01-06T03:00:00Z",
                "bid_high": 102.2,
                "bid_low": 100.0,
            },
        ]
    )

    result = run_engine(bars, _config())

    assert result.signals == 3
    assert len(result.trades) == 2
    assert result.trades["r_multiple"].tolist() == pytest.approx([-1.4, -1.4])
    assert result.skipped_by_vol_ceiling == 0


def test_friday_no_entry_cutoff_uses_entry_bar_utc_time():
    bars = _bars(
        [
            {"timestamp_utc": "2025-01-10T18:00:00Z", "signal": 1},
            {
                "timestamp_utc": "2025-01-10T19:00:00Z",
                "bid_high": 103.0,
            },
        ]
    )

    result = run_engine(bars, _config())

    assert result.signals == 1
    assert result.trades.empty


def test_trade_open_across_recorded_gap_is_flagged_gap_risk():
    bars = _bars(
        [
            {"timestamp_utc": "2025-01-06T00:00:00Z", "signal": 1},
            {"timestamp_utc": "2025-01-06T01:00:00Z"},
            {
                "timestamp_utc": "2025-01-06T08:00:00Z",
                "bid_high": 102.2,
                "bid_low": 100.0,
            },
        ]
    )
    gaps = pd.DataFrame(
        {
            "gap_start": [pd.Timestamp("2025-01-06T01:00:00Z")],
            "gap_end": [pd.Timestamp("2025-01-06T08:00:00Z")],
            "gap_hours": [7.0],
            "gap_kind": ["session"],
        }
    )

    trade = run_engine(bars, _config(), gaps=gaps).trades.iloc[0]

    assert trade["flags"] == "gap_risk"


def test_minimum_stop_distance_sets_r_geometry_when_atr_is_small():
    bars = _bars(
        [
            {
                "timestamp_utc": "2025-01-06T00:00:00Z",
                "signal": 1,
                "atr": 0.2,
                "ask_close": 100.05,
            },
            {
                "timestamp_utc": "2025-01-06T01:00:00Z",
                "bid_high": 101.1,
                "bid_low": 99.8,
            },
        ]
    )

    trade = run_engine(bars, _config()).trades.iloc[0]

    assert trade["atr"] == pytest.approx(0.2)
    assert trade["stop"] == pytest.approx(99.5)
    assert trade["target"] == pytest.approx(101.0)
    assert trade["r_multiple"] == pytest.approx(1.2)


def test_open_trade_is_closed_on_final_bar_without_being_dropped():
    bars = _bars(
        [
            {"timestamp_utc": "2025-01-06T00:00:00Z", "signal": 1},
            {
                "timestamp_utc": "2025-01-06T01:00:00Z",
                "bid_close": 100.1,
            },
        ]
    )

    trade = run_engine(bars, _config()).trades.iloc[0]

    assert trade["exit"] == pytest.approx(100.1)
    assert trade["r_multiple"] == pytest.approx(-0.3)
    assert trade["exit_reason"] == "end_of_data"


def test_raw_bars_are_prepared_with_aroon_series_and_simple_atr():
    bars = _bars(
        [
            {
                "timestamp_utc": "2025-01-06T00:00:00Z",
                "bid_high": 103.0,
                "bid_low": 102.0,
                "bid_close": 102.5,
            },
            {
                "timestamp_utc": "2025-01-06T01:00:00Z",
                "bid_high": 105.0,
                "bid_low": 101.0,
                "bid_close": 104.0,
            },
            {
                "timestamp_utc": "2025-01-06T02:00:00Z",
                "bid_high": 104.0,
                "bid_low": 102.0,
                "bid_close": 103.0,
            },
            {
                "timestamp_utc": "2025-01-06T03:00:00Z",
                "bid_high": 106.0,
                "bid_low": 103.0,
                "bid_close": 105.0,
            },
            {
                "timestamp_utc": "2025-01-06T04:00:00Z",
                "bid_high": 108.0,
                "bid_low": 100.0,
                "bid_close": 107.0,
            },
        ]
    ).drop(columns=["signal", "atr"])
    for side in ("open", "high", "low", "close"):
        bars[f"ask_{side}"] = bars[f"bid_{side}"] + 0.2

    prepared = prepare_bars(
        bars,
        _config(aroon_period=3, threshold=50, ties="newest"),
        atr_period=2,
    )

    assert prepared["signal"].tolist() == [0, 0, 0, 1, 0]
    assert prepared["atr"].iloc[:1].isna().all()
    assert prepared["atr"].iloc[1:].notna().all()

    result = run_engine(
        bars,
        _config(aroon_period=3, threshold=50, ties="newest"),
        atr_period=2,
    )

    assert result.signals == 1
    assert len(result.trades) == 1
