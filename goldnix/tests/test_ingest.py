"""Behaviour tests for XAUUSD ingestion and spread profiling."""

import pandas as pd
import pytest

from ingest.ingest import (
    SYNTHETIC_SPREAD_WARNING,
    load_bars,
    spread_distribution_by_year,
    spread_issues,
    synthetic_spread_warning,
)


def test_spread_distribution_uses_open_and_close_quote_sides_by_year():
    bars = pd.DataFrame(
        {
            "timestamp_utc": pd.to_datetime(
                ["2024-01-01T00:00:00Z", "2024-01-01T01:00:00Z", "2024-01-01T02:00:00Z"]
            ),
            "bid_open": [100.0, 101.0, 102.0],
            "ask_open": [100.4, 101.4, 102.8],
            "bid_close": [100.1, 101.1, 102.1],
            "ask_close": [100.6, 101.6, 102.8],
        }
    )

    report = spread_distribution_by_year(bars).set_index("spread_kind")

    assert report.loc["entry", "min"] == pytest.approx(0.4)
    assert report.loc["entry", "p5"] == pytest.approx(0.4)
    assert report.loc["entry", "median"] == pytest.approx(0.4)
    assert report.loc["entry", "p95"] == pytest.approx(0.76)
    assert report.loc["entry", "max"] == pytest.approx(0.8)
    assert report.loc["entry", "modal_share"] == pytest.approx(2 / 3)
    assert report.loc["ceiling", "min"] == pytest.approx(0.5)
    assert report.loc["ceiling", "p95"] == pytest.approx(0.68)
    assert report.loc["ceiling", "max"] == pytest.approx(0.7)
    assert report.loc["ceiling", "modal_share"] == pytest.approx(2 / 3)
    assert report["year"].tolist() == [2024, 2024]


def test_load_bars_parses_utc_deduplicates_and_sorts(tmp_path):
    source = tmp_path / "bars.csv"
    source.write_text(
        "timestamp_utc,value\n"
        "2024-01-01T01:00:00Z,3\n"
        "2024-01-01T00:00:00Z,1\n"
        "2024-01-01T00:00:00Z,1\n",
        encoding="utf-8",
    )

    bars = load_bars(source)

    assert bars["timestamp_utc"].tolist() == [
        pd.Timestamp("2024-01-01T00:00:00Z"),
        pd.Timestamp("2024-01-01T01:00:00Z"),
    ]
    assert str(bars["timestamp_utc"].dtype) == "datetime64[ns, UTC]"
    assert bars["timestamp_utc"].is_unique
    assert bars["timestamp_utc"].is_monotonic_increasing


def test_spread_issues_flags_each_approved_spread_definition():
    bars = pd.DataFrame(
        {
            "timestamp_utc": pd.to_datetime(
                ["2024-01-01T00:00:00Z", "2024-01-01T01:00:00Z", "2024-01-01T02:00:00Z"]
            ),
            "bid_open": [100.0, 100.0, 100.0],
            "ask_open": [100.0, 101.2, 100.4],
            "bid_close": [100.0, 100.0, 100.0],
            "ask_close": [100.2, 100.0, 101.1],
        }
    )

    issues = spread_issues(bars)

    assert issues[["spread_kind", "issue"]].value_counts().to_dict() == {
        ("entry", "non_positive"): 1,
        ("entry", "above_1_usd"): 1,
        ("ceiling", "non_positive"): 1,
        ("ceiling", "above_1_usd"): 1,
    }


def test_essentially_constant_spread_prints_the_required_warning():
    bars = pd.DataFrame(
        {
            "timestamp_utc": pd.date_range("2024-01-01", periods=20, freq="h", tz="UTC"),
            "bid_open": [100.0] * 20,
            "ask_open": [100.41] * 20,
            "bid_close": [100.1] * 20,
            "ask_close": [100.51] * 20,
        }
    )

    assert synthetic_spread_warning(bars) == SYNTHETIC_SPREAD_WARNING
