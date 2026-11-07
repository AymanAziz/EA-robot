from __future__ import annotations

import io
import hashlib
import json
import math
import sys
import zipfile
from dataclasses import replace
from datetime import date

import httpx
import pandas as pd
import pytest

import papertrade.stock_quality as stock_quality_module
from papertrade.stock_quality import (
    DEVELOPED_FACTORS_DAILY_URL,
    DEVELOPED_FACTORS_DAILY_SHA256,
    DEVELOPED_PROFITABILITY_DAILY_URL,
    DEVELOPED_PROFITABILITY_DAILY_SHA256,
    KennethFrenchDevelopedHistory,
    SOURCE_ID,
    StockQualityHistory,
    StockQualityStrategySpec,
    run_stock_quality_target_command,
    run_stock_quality_target_test,
)


def test_stock_quality_pinned_source_digests_are_full_sha256_values():
    for digest in (
        DEVELOPED_FACTORS_DAILY_SHA256,
        DEVELOPED_PROFITABILITY_DAILY_SHA256,
    ):
        assert len(digest) == 64
        assert int(digest, 16) >= 0


def _synthetic_stock_quality_history() -> StockQualityHistory:
    rows = []
    for index, stamp in enumerate(pd.bdate_range("1991-07-01", "2025-12-31")):
        rows.append({
            "date": stamp.date().isoformat(),
            "market_return_percent": 0.03 + 0.01 * math.sin(index / 19),
            "big_robust_return_percent": 0.05 + 0.015 * math.cos(index / 23),
            "risk_free_return_percent": 0.01,
        })
    return StockQualityHistory(
        rows=tuple(rows),
        manifest=({"fixture": "developed-market-and-big-robust"},),
    )


def test_stock_quality_target_runs_two_locked_windows_with_independent_equity_resets():
    history = _synthetic_stock_quality_history()
    spec = StockQualityStrategySpec()

    report = run_stock_quality_target_test(history, spec)

    assert run_stock_quality_target_test(history, spec) == report
    assert report["spec_sha256"] == spec.sha256
    assert report["source_manifest"] == [{"fixture": "developed-market-and-big-robust"}]
    assert report["strategy"] == {
        "developed_market_weight": 0.8,
        "big_robust_weight": 0.2,
        "rebalance": "quarterly",
        "leverage": 1.0,
        "shorting": False,
    }
    assert report["test_a"]["date_range"] == {
        "start": "1991-07-01",
        "end": "2007-12-31",
    }
    assert report["test_b"]["date_range"] == {
        "start": "2008-01-01",
        "end": "2025-12-31",
    }
    assert report["test_a"]["starting_equity_usd"] == 10_000.0
    assert report["test_b"]["starting_equity_usd"] == 10_000.0
    assert report["test_a"]["complete_weeks"] >= 260
    assert report["test_b"]["complete_weeks"] >= 260
    assert report["overall_status"] in {"pass", "fail", "inconclusive"}
    assert report["warning"].endswith("not proof of future weekly profit or an executable trade.")


def test_stock_quality_weekly_profit_uses_a_fixed_10k_base_instead_of_compounded_equity():
    rows = tuple({
        "date": stamp.date().isoformat(),
        "market_return_percent": 1.0,
        "big_robust_return_percent": 1.0,
        "risk_free_return_percent": 0.0,
    } for stamp in pd.bdate_range("2024-01-01", "2024-02-29"))
    history = StockQualityHistory(rows=rows, manifest=({"fixture": "constant-one-percent"},))
    spec = replace(
        StockQualityStrategySpec(),
        market_annual_drag=0.0,
        big_robust_annual_drag=0.0,
        transaction_cost_bps=0.0,
        minimum_complete_weeks=1,
        bootstrap_samples=100,
        test_a_start=date(2024, 1, 1),
        test_a_end=date(2024, 1, 29),
        test_b_start=date(2024, 2, 1),
        test_b_end=date(2024, 2, 29),
    )

    report = run_stock_quality_target_test(history, spec)

    expected_week = 10_000 * (1.01**5 - 1)
    assert report["test_a"]["weekly_pl_usd"][:2] == pytest.approx(
        [expected_week, expected_week]
    )
    assert report["test_a"]["mean_weekly_net_pl_usd"] == pytest.approx(expected_week)
    assert sum(report["test_a"]["weekly_pl_usd"]) != pytest.approx(
        report["test_a"]["ending_equity_usd"] - 10_000
    )


def test_stock_quality_transaction_costs_are_literal_and_self_financing():
    rows = tuple({
        "date": stamp.date().isoformat(),
        "market_return_percent": 0.02,
        "big_robust_return_percent": 0.04,
        "risk_free_return_percent": 0.0,
    } for stamp in pd.bdate_range("2024-01-01", "2024-04-30"))
    history = StockQualityHistory(rows=rows, manifest=({"fixture": "literal-costs"},))
    spec = replace(
        StockQualityStrategySpec(),
        market_annual_drag=0.0,
        big_robust_annual_drag=0.0,
        minimum_complete_weeks=4,
        bootstrap_samples=100,
        test_a_start=date(2024, 1, 1),
        test_a_end=date(2024, 2, 29),
        test_b_start=date(2024, 3, 1),
        test_b_end=date(2024, 4, 30),
    )

    report = run_stock_quality_target_test(history, spec)

    for name in ("test_a", "test_b"):
        events = report[name]["cost_events"]
        entry = events[0]
        assert entry["event"] == "entry"
        assert entry["cost_usd"] == pytest.approx(
            entry["traded_notional_usd"] * spec.transaction_cost_bps / 10_000
        )
        assert entry["traded_notional_usd"] + entry["cost_usd"] == pytest.approx(
            spec.initial_equity_usd
        )
        for event in events:
            assert event["cost_usd"] == pytest.approx(
                event["traded_notional_usd"] * spec.transaction_cost_bps / 10_000
            )


def test_stock_quality_rejects_short_or_leveraged_target_weights():
    history = _synthetic_stock_quality_history()
    spec = replace(
        StockQualityStrategySpec(),
        developed_market_weight=1.2,
        big_robust_weight=-0.2,
    )

    with pytest.raises(ValueError, match="no shorting or leverage"):
        run_stock_quality_target_test(history, spec)


def test_stock_quality_pass_requires_profitable_weeks_and_paired_market_excess():
    rows = tuple({
        "date": stamp.date().isoformat(),
        "market_return_percent": 0.0,
        "big_robust_return_percent": 0.30,
        "risk_free_return_percent": 0.0,
    } for stamp in pd.bdate_range("2024-01-01", "2024-04-30"))
    history = StockQualityHistory(rows=rows, manifest=({"fixture": "quality-excess"},))
    spec = replace(
        StockQualityStrategySpec(),
        market_annual_drag=0.0,
        big_robust_annual_drag=0.0,
        transaction_cost_bps=0.0,
        minimum_complete_weeks=4,
        bootstrap_samples=500,
        test_a_start=date(2024, 1, 1),
        test_a_end=date(2024, 2, 29),
        test_b_start=date(2024, 3, 1),
        test_b_end=date(2024, 4, 30),
    )

    report = run_stock_quality_target_test(history, spec)

    assert report["overall_status"] == "pass"
    for name in ("test_a", "test_b"):
        result = report[name]
        assert result["status"] == "pass"
        assert all(result["gates"].values())
        assert result["profitable_weeks_percentage"] > 50.0
        assert result["bootstrap_95_lower_mean_weekly_pl_usd"] > 20.0
        assert result["bootstrap_95_lower_mean_weekly_excess_usd"] > 0.0
        assert result["weekly_excess_over_market_usd"] == pytest.approx([
            strategy - benchmark
            for strategy, benchmark in zip(
                result["weekly_pl_usd"], result["benchmark_weekly_pl_usd"], strict=True
            )
        ])


def test_stock_quality_fails_when_the_observed_mean_does_not_clear_20_usd():
    rows = tuple({
        "date": stamp.date().isoformat(),
        "market_return_percent": 0.0,
        "big_robust_return_percent": 0.05,
        "risk_free_return_percent": 0.0,
    } for stamp in pd.bdate_range("2024-01-01", "2024-04-30"))
    history = StockQualityHistory(rows=rows, manifest=({"fixture": "below-target"},))
    spec = replace(
        StockQualityStrategySpec(),
        market_annual_drag=0.0,
        big_robust_annual_drag=0.0,
        transaction_cost_bps=0.0,
        minimum_complete_weeks=4,
        bootstrap_samples=100,
        test_a_start=date(2024, 1, 1),
        test_a_end=date(2024, 2, 29),
        test_b_start=date(2024, 3, 1),
        test_b_end=date(2024, 4, 30),
    )

    report = run_stock_quality_target_test(history, spec)

    assert report["overall_status"] == "fail"
    for name in ("test_a", "test_b"):
        result = report[name]
        assert result["mean_weekly_net_pl_usd"] <= 20.0
        assert result["status"] == "fail"
        assert "mean fixed-base weekly net P/L above USD 20" in result["failed_gates"]


def test_stock_quality_is_inconclusive_when_the_locked_window_is_too_short():
    rows = tuple({
        "date": stamp.date().isoformat(),
        "market_return_percent": 0.0,
        "big_robust_return_percent": 0.30,
        "risk_free_return_percent": 0.0,
    } for stamp in pd.bdate_range("2024-01-01", "2024-04-30"))
    history = StockQualityHistory(rows=rows, manifest=({"fixture": "short-window"},))
    spec = replace(
        StockQualityStrategySpec(),
        market_annual_drag=0.0,
        big_robust_annual_drag=0.0,
        transaction_cost_bps=0.0,
        bootstrap_samples=100,
        test_a_start=date(2024, 1, 1),
        test_a_end=date(2024, 2, 29),
        test_b_start=date(2024, 3, 1),
        test_b_end=date(2024, 4, 30),
    )

    report = run_stock_quality_target_test(history, spec)

    assert report["overall_status"] == "inconclusive"
    for name in ("test_a", "test_b"):
        assert report[name]["status"] == "inconclusive"
        assert report[name]["classification_reason"] == "fewer than 260 complete weeks"


def test_stock_quality_command_reuses_verified_private_cache_and_is_byte_deterministic(
    tmp_path, monkeypatch
):
    rows = tuple({
        "date": stamp.date().isoformat(),
        "market_return_percent": 0.0,
        "big_robust_return_percent": 0.30,
        "risk_free_return_percent": 0.0,
    } for stamp in pd.bdate_range("2024-01-01", "2024-04-30"))
    history = _cacheable_history(rows, monkeypatch)

    class Source:
        def __init__(self):
            self.calls = 0

        def fetch(self):
            self.calls += 1
            return history

    source = Source()
    spec = replace(
        StockQualityStrategySpec(),
        market_annual_drag=0.0,
        big_robust_annual_drag=0.0,
        transaction_cost_bps=0.0,
        minimum_complete_weeks=4,
        bootstrap_samples=100,
        test_a_start=date(2024, 1, 1),
        test_a_end=date(2024, 2, 29),
        test_b_start=date(2024, 3, 1),
        test_b_end=date(2024, 4, 30),
    )
    cache_path = tmp_path / "stock-quality-cache.json"
    first_report = tmp_path / "report-1.json"
    second_report = tmp_path / "report-2.json"

    first = run_stock_quality_target_command(
        cache_path, first_report, source=source, spec=spec
    )
    second = run_stock_quality_target_command(
        cache_path, second_report, source=source, spec=spec
    )

    assert first == second
    assert source.calls == 1
    assert first_report.read_bytes() == second_report.read_bytes()
    assert cache_path.stat().st_mode & 0o777 == 0o600
    assert first_report.stat().st_mode & 0o777 == 0o600
    assert second_report.stat().st_mode & 0o777 == 0o600


def _zip_csv(member: str, text: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(member, text)
    return buffer.getvalue()


def _source_payloads(rows) -> tuple[bytes, bytes]:
    factors = "\n".join([
        "Created for a cache fixture",
        ",Mkt-RF,SMB,HML,RMW,CMA,RF",
        *(
            f"{row['date'].replace('-', '')},"
            f"{row['market_return_percent'] - row['risk_free_return_percent']},"
            f"0,0,0,0,{row['risk_free_return_percent']}"
            for row in rows
        ),
    ])
    portfolios = "\n".join([
        "Created for a cache fixture",
        "Average Value Weighted Returns -- Daily",
        "                 Small                 Big",
        ",SMALL LoBO,ME1 BO2,SMALL HiBO,BIG LoBO,ME2 BO2,BIG HiBO",
        *(
            f"{row['date'].replace('-', '')},0,0,0,0,0,{row['big_robust_return_percent']}"
            for row in rows
        ),
    ])
    return (
        _zip_csv("Developed_5_Factors_Daily.csv", factors),
        _zip_csv("Developed_6_Portfolios_ME_OP_Daily.csv", portfolios),
    )


def _cacheable_history(rows, monkeypatch) -> StockQualityHistory:
    payloads = _source_payloads(rows)
    monkeypatch.setattr(
        stock_quality_module,
        "DEVELOPED_FACTORS_DAILY_SHA256",
        hashlib.sha256(payloads[0]).hexdigest(),
    )
    monkeypatch.setattr(
        stock_quality_module,
        "DEVELOPED_PROFITABILITY_DAILY_SHA256",
        hashlib.sha256(payloads[1]).hexdigest(),
    )
    by_url = {
        DEVELOPED_FACTORS_DAILY_URL: payloads[0],
        DEVELOPED_PROFITABILITY_DAILY_URL: payloads[1],
    }

    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=by_url[str(request.url)])

    return KennethFrenchDevelopedHistory(
        client=httpx.Client(transport=httpx.MockTransport(respond))
    ).fetch()


def test_stock_quality_command_parses_only_the_official_value_weighted_big_robust_section(
    tmp_path, monkeypatch,
):
    dates = [stamp.strftime("%Y%m%d") for stamp in pd.bdate_range("2024-01-01", "2024-04-30")]
    factors = "\n".join([
        "Created for a parser fixture",
        ",Mkt-RF,SMB,HML,RMW,CMA,RF",
        *(f"{stamp},0.00,0.00,0.00,0.00,0.00,0.00" for stamp in dates),
    ])
    portfolios = "\n".join([
        "Created for a parser fixture",
        "Average Value Weighted Returns -- Daily",
        "                 Small                 Big",
        ",SMALL LoBO,ME1 BO2,SMALL HiBO,BIG LoBO,ME2 BO2,BIG HiBO",
        *(f"{stamp},0.00,0.00,0.00,0.00,0.00,0.30" for stamp in dates),
        "Average Equal Weighted Returns -- Daily",
        ",SMALL LoBO,ME1 BO2,SMALL HiBO,BIG LoBO,ME2 BO2,BIG HiBO",
        *(f"{stamp},0.00,0.00,0.00,0.00,0.00,99.00" for stamp in dates),
    ])
    payloads = {
        DEVELOPED_FACTORS_DAILY_URL: _zip_csv("Developed_5_Factors_Daily.csv", factors),
        DEVELOPED_PROFITABILITY_DAILY_URL: _zip_csv(
            "Developed_6_Portfolios_ME_OP_Daily.csv", portfolios
        ),
    }
    monkeypatch.setattr(
        stock_quality_module,
        "DEVELOPED_FACTORS_DAILY_SHA256",
        hashlib.sha256(payloads[DEVELOPED_FACTORS_DAILY_URL]).hexdigest(),
    )
    monkeypatch.setattr(
        stock_quality_module,
        "DEVELOPED_PROFITABILITY_DAILY_SHA256",
        hashlib.sha256(payloads[DEVELOPED_PROFITABILITY_DAILY_URL]).hexdigest(),
    )
    requested = []

    def respond(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        return httpx.Response(
            200,
            content=payloads[str(request.url)],
            headers={"ETag": '"fixture"', "Last-Modified": "Sat, 07 Nov 2026 00:00:00 GMT"},
        )

    source = KennethFrenchDevelopedHistory(
        client=httpx.Client(transport=httpx.MockTransport(respond))
    )
    spec = replace(
        StockQualityStrategySpec(),
        market_annual_drag=0.0,
        big_robust_annual_drag=0.0,
        transaction_cost_bps=0.0,
        minimum_complete_weeks=4,
        bootstrap_samples=100,
        test_a_start=date(2024, 1, 1),
        test_a_end=date(2024, 2, 29),
        test_b_start=date(2024, 3, 1),
        test_b_end=date(2024, 4, 30),
    )
    cache_path = tmp_path / "official-cache.json"

    report = run_stock_quality_target_command(
        cache_path, tmp_path / "official-report.json", source=source, spec=spec
    )

    assert requested == [DEVELOPED_FACTORS_DAILY_URL, DEVELOPED_PROFITABILITY_DAILY_URL]
    assert report["overall_status"] == "pass"
    cached = json.loads(cache_path.read_text())
    assert cached["rows"][0]["big_robust_return_percent"] == 0.30
    assert [item["role"] for item in cached["manifest"]] == [
        "developed_five_factors_daily",
        "developed_size_profitability_daily",
    ]
    assert all(len(item["response_sha256"]) == 64 for item in cached["manifest"])
    assert len(cached["payloads_base64"]) == 2

    cached["rows"][0]["big_robust_return_percent"] = 50.0
    material = {
        "source_id": SOURCE_ID,
        "manifest": cached["manifest"],
        "rows": cached["rows"],
    }
    cached["rows_sha256"] = hashlib.sha256(json.dumps(
        material, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()).hexdigest()
    cache_path.write_text(json.dumps(cached))

    with pytest.raises(ValueError, match="raw source payload"):
        run_stock_quality_target_command(
            cache_path, tmp_path / "tampered-report.json", source=source, spec=spec
        )


def test_stock_quality_command_rejects_rehashed_cache_with_altered_source_provenance(
    tmp_path, monkeypatch
):
    rows = tuple({
        "date": stamp.date().isoformat(),
        "market_return_percent": 0.0,
        "big_robust_return_percent": 0.30,
        "risk_free_return_percent": 0.0,
    } for stamp in pd.bdate_range("2024-01-01", "2024-04-30"))
    history = _cacheable_history(rows, monkeypatch)

    class Source:
        def fetch(self):
            return history

    spec = replace(
        StockQualityStrategySpec(),
        minimum_complete_weeks=4,
        bootstrap_samples=100,
        test_a_start=date(2024, 1, 1),
        test_a_end=date(2024, 2, 29),
        test_b_start=date(2024, 3, 1),
        test_b_end=date(2024, 4, 30),
    )
    cache_path = tmp_path / "provenance-cache.json"
    run_stock_quality_target_command(
        cache_path, tmp_path / "seed-report.json", source=Source(), spec=spec
    )
    cached = json.loads(cache_path.read_text())
    cached["manifest"][0]["url"] = "https://example.invalid/not-dartmouth.zip"
    material = {
        "source_id": SOURCE_ID,
        "manifest": cached["manifest"],
        "rows": cached["rows"],
    }
    cached["rows_sha256"] = hashlib.sha256(json.dumps(
        material, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()).hexdigest()
    cache_path.write_text(json.dumps(cached))

    with pytest.raises(ValueError, match="provenance"):
        run_stock_quality_target_command(
            cache_path, tmp_path / "rejected-report.json", source=Source(), spec=spec
        )


def test_stock_quality_cli_writes_bounded_status_without_initializing_trading(
    tmp_path, monkeypatch, capsys
):
    from papertrade import cli
    from papertrade.brokers.alpaca import AlpacaPaper
    from papertrade.brokers.oanda import OandaPractice
    from papertrade.brokers.simulator import LocalPaperSimulator

    base = _synthetic_stock_quality_history()
    history = _cacheable_history(base.rows, monkeypatch)

    class Source:
        def fetch(self):
            return history

    cache_path = tmp_path / "cli-cache.json"
    run_stock_quality_target_command(
        cache_path, tmp_path / "seed-report.json", source=Source()
    )
    report_path = tmp_path / "cli-report.json"

    def forbidden(*_args, **_kwargs):
        raise AssertionError("research command crossed into trading initialization")

    monkeypatch.setattr(cli, "Settings", forbidden)
    monkeypatch.setattr(cli, "Database", forbidden)
    monkeypatch.setattr(cli, "configure_logging", forbidden)
    monkeypatch.setattr("papertrade.engine.TradingEngine", forbidden)
    monkeypatch.setattr("papertrade.brokers.factory.build_brokers", forbidden)
    monkeypatch.setattr(AlpacaPaper, "submit_order", forbidden)
    monkeypatch.setattr(OandaPractice, "submit_order", forbidden)
    monkeypatch.setattr(LocalPaperSimulator, "submit_order", forbidden)
    monkeypatch.setattr(sys, "argv", [
        "papertrade",
        "stock-quality-target",
        "--cache",
        str(cache_path),
        "--report",
        str(report_path),
    ])

    cli.main()

    shown = json.loads(capsys.readouterr().out)
    saved = json.loads(report_path.read_text())
    assert shown == {
        "report": str(report_path),
        "overall_status": saved["overall_status"],
        "test_a": saved["test_a"]["status"],
        "test_b": saved["test_b"]["status"],
        "warning": saved["warning"],
    }
