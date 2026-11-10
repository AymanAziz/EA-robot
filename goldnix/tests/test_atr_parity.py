"""Behaviour tests for ATR parity method selection."""

import pandas as pd
import pytest

from parity.atr_parity import (
    compare_atr_methods,
    convert_server_time_to_utc,
    load_mt5_export,
)


def test_parity_selects_only_method_below_one_cent_maximum_error():
    exported = pd.DataFrame(
        {
            "high": [10.0, 12.0, 13.0, 15.0, 14.0],
            "low": [8.0, 9.0, 11.0, 12.0, 10.0],
            "close": [9.0, 11.0, 12.0, 13.0, 11.0],
            "mt5_atr": [0.0, 0.0, 7 / 3, 23 / 9, 82 / 27],
            "compare": [False, False, True, True, True],
        }
    )

    result = compare_atr_methods(exported, period=3)

    assert result.simple_max_abs_difference == pytest.approx(1 / 9)
    assert result.wilder_max_abs_difference == pytest.approx(0.0)
    assert result.chosen_method == "wilder"
    assert result.passed is True


def test_mt5_export_loader_preserves_server_time_and_orders_oldest_first(tmp_path):
    export = tmp_path / "atr.csv"
    export.write_text(
        "account_server,symbol,server_time,server_utc_offset_seconds,high,low,close,mt5_atr,compare\n"
        "MetaQuotes-Demo,XAUUSD,2026.11.10 11:00:00,7200,10,8,9,2.5,1\n"
        "MetaQuotes-Demo,XAUUSD,2026.11.10 10:00:00,7200,9,7,8,2.4,0\n",
        encoding="utf-8",
    )

    loaded = load_mt5_export(export)

    assert loaded["server_time"].dt.tz is None
    assert loaded["server_time"].is_monotonic_increasing
    assert loaded["compare"].tolist() == [False, True]


def test_metaquotes_demo_conversion_uses_european_dst_by_historical_date():
    server_time = pd.Series(
        pd.to_datetime(
            [
                "2026-03-27 12:00:00",
                "2026-03-30 12:00:00",
                "2026-10-23 12:00:00",
                "2026-10-26 12:00:00",
            ]
        )
    )

    converted = convert_server_time_to_utc(server_time)

    assert converted.tolist() == [
        pd.Timestamp("2026-03-27 10:00:00Z"),
        pd.Timestamp("2026-03-30 09:00:00Z"),
        pd.Timestamp("2026-10-23 09:00:00Z"),
        pd.Timestamp("2026-10-26 10:00:00Z"),
    ]
