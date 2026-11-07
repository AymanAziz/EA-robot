from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import date
import json
import math
import sys

import httpx
import pandas as pd
import pytest

from papertrade.gold_weekly import (
    AlgoSpecialGoldDailyHistory,
    DailyGoldHistory,
    GoldWeeklyStrategySpec,
    classify_weekly_target_evidence,
    classify_weekly_target_pair,
    prepare_daily_gold_history,
    run_gold_weekly_target_test,
    run_gold_weekly_target_command,
)


def test_public_weekly_evidence_classifier_distinguishes_fail_inconclusive_and_pass():
    common = {
        "maximum_drawdown": -0.05,
        "buy_hold_net_pl_usd": 0.0,
        "notional_cap_breached": False,
    }

    failed = classify_weekly_target_evidence([10.0, 12.0] * 26, **common)
    uncertain = classify_weekly_target_evidence([100.0] * 26 + [-50.0] * 26, **common)
    passed = classify_weekly_target_evidence([29.0, 31.0] * 26, **common)

    assert failed["mean_weekly_net_pl_usd"] == pytest.approx(11.0)
    assert failed["status"] == "fail"
    assert uncertain["mean_weekly_net_pl_usd"] == pytest.approx(25.0)
    assert uncertain["bootstrap_95_lower_mean_weekly_pl_usd"] <= 20.0
    assert uncertain["status"] == "inconclusive"
    assert passed["bootstrap_95_lower_mean_weekly_pl_usd"] > 20.0
    assert passed["status"] == "pass"


def test_public_weekly_pair_classifier_uses_fail_then_inconclusive_precedence():
    assert classify_weekly_target_pair({"status": "pass"}, {"status": "pass"}) == "pass"
    assert classify_weekly_target_pair(
        {"status": "pass"}, {"status": "inconclusive"}
    ) == "inconclusive"
    assert classify_weekly_target_pair(
        {"status": "inconclusive"}, {"status": "fail"}
    ) == "fail"


def test_weekly_strategy_spec_is_immutable_and_locks_the_usd_target_contract():
    spec = GoldWeeklyStrategySpec()

    assert spec.initial_equity_usd == 10_000.0
    assert spec.momentum_months == (1, 3, 12)
    assert spec.volatility_months == 12
    assert spec.annual_volatility_target == 0.10
    assert spec.maximum_notional_multiple == 1.0
    assert spec.target_weekly_profit_usd == 20.0
    assert spec.minimum_complete_weeks == 52
    assert spec.financing_rates == (0.05, 0.10, 0.15)
    assert spec.primary_financing_rate == 0.10
    assert spec.strategy_version == "gold_weekly_tsm_v1"
    assert spec.execution_timing == "completed month signal; first next-month D1 open"
    assert spec.account_margin_rule == (
        "broker account margin unavailable; research-only; not evaluated as a pass gate"
    )
    assert spec.bootstrap_quantile == 0.05
    assert len(spec.sha256) == 64
    assert spec.sha256 == GoldWeeklyStrategySpec().sha256
    with pytest.raises(FrozenInstanceError):
        spec.target_weekly_profit_usd = 1.0


def test_daily_history_fetches_verified_inclusive_thirty_one_day_chunks():
    requests = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        start = request.url.params["from"]
        row = {
            "Timestamp": f"{start.replace('-', '.')} 00:00:00",
            "Open": 1_900.0,
            "High": 1_910.0,
            "Low": 1_890.0,
            "Close": 1_905.0,
            "TickVolume": 100,
            "Spread": 200,
        }
        return httpx.Response(200, json={
            "symbol": "XAUUSD",
            "timeframe": "D1",
            "from": start,
            "to": request.url.params["to"],
            "rows": 1,
            "data": [row],
        })

    client = httpx.Client(transport=httpx.MockTransport(respond))

    history = AlgoSpecialGoldDailyHistory(client=client).fetch(
        date(2023, 1, 1), date(2023, 2, 5)
    )

    assert [(item.url.params["from"], item.url.params["to"], item.url.params["tf"])
            for item in requests] == [
        ("2023-01-01", "2023-01-31", "D1"),
        ("2023-02-01", "2023-02-05", "D1"),
    ]
    assert len(history.rows) == 2
    assert [item["returned_rows"] for item in history.manifest] == [1, 1]
    assert all(item["timeframe"] == "D1" for item in history.manifest)
    assert all(len(item["chunk_sha256"]) == 64 for item in history.manifest)
    with pytest.raises(TypeError):
        history.rows[0]["Open"] = 1.0


def test_prepare_daily_history_preserves_provider_clock_and_validates_prices_and_spread():
    rows = (
        {"Timestamp": "2020.01.02 00:00:00", "Open": 1_500.0, "High": 1_510.0,
         "Low": 1_490.0, "Close": 1_505.0, "TickVolume": 100, "Spread": 240},
        {"Timestamp": "2020.01.03 00:00:00", "Open": 1_505.0, "High": 1_515.0,
         "Low": 1_500.0, "Close": 1_510.0, "TickVolume": 120, "Spread": 0},
    )
    history = DailyGoldHistory(rows=rows, manifest=({"fixture": "daily"},))

    prepared = prepare_daily_gold_history(history)

    assert prepared.source_id == "algospecial_xauusd_d1_preview"
    assert prepared.frame.index.name == "provider_time"
    assert prepared.frame.index.tz is None
    assert prepared.frame.index.tolist() == [pd.Timestamp("2020-01-02"), pd.Timestamp("2020-01-03")]
    assert prepared.frame["spread_usd"].tolist() == [0.24, 0.0]
    assert len(prepared.data_sha256) == 64

    bad = dict(rows[0], Spread=-1)
    with pytest.raises(ValueError, match="finite nonnegative spread"):
        prepare_daily_gold_history(DailyGoldHistory(rows=(bad,), manifest=()))


def _synthetic_daily_history() -> DailyGoldHistory:
    rows = []
    dates = pd.date_range("2020-12-01", "2023-12-31", freq="D")
    for index, stamp in enumerate(dates):
        center = 1_250.0 * math.exp(index * 0.00015 + 0.08 * math.sin(index / 170))
        opening = center * (1 + 0.001 * math.sin(index / 11))
        closing = center * (1 + 0.001 * math.cos(index / 13))
        rows.append({
            "Timestamp": stamp.strftime("%Y.%m.%d 00:00:00"),
            "Open": round(opening, 3),
            "High": round(max(opening, closing) * 1.003, 3),
            "Low": round(min(opening, closing) * 0.997, 3),
            "Close": round(closing, 3),
            "TickVolume": 1_000 + index % 100,
            "Spread": 200,
        })
    return DailyGoldHistory(rows=tuple(rows), manifest=({"fixture": "daily-trend"},))


def _mock_daily_source(*, duplicate_first: bool = False):
    history = _synthetic_daily_history()
    raw_rows = [dict(row) for row in history.rows]
    requests = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        start = date.fromisoformat(request.url.params["from"])
        end = date.fromisoformat(request.url.params["to"])
        selected = [row for row in raw_rows if start <= pd.Timestamp(
            row["Timestamp"]
        ).date() <= end]
        if duplicate_first and not requests[:-1] and selected:
            selected.insert(1, dict(selected[0]))
        return httpx.Response(200, json={
            "symbol": "XAUUSD",
            "timeframe": "D1",
            "from": start.isoformat(),
            "to": end.isoformat(),
            "rows": len(selected),
            "data": selected,
        })

    source = AlgoSpecialGoldDailyHistory(
        client=httpx.Client(transport=httpx.MockTransport(respond))
    )
    return source, requests


def test_weekly_target_runs_two_locked_calendar_year_holdouts_with_equity_reset():
    prepared = prepare_daily_gold_history(_synthetic_daily_history())
    spec = GoldWeeklyStrategySpec()

    report = run_gold_weekly_target_test(prepared, spec)
    repeated = run_gold_weekly_target_test(prepared, spec)

    assert repeated == report
    assert report["spec_sha256"] == spec.sha256
    assert report["data_sha256"] == prepared.data_sha256
    assert report["test_a"]["complete_weeks"] == 52
    assert report["test_b"]["complete_weeks"] == 52
    assert report["test_a"]["starting_equity_usd"] == 10_000.0
    assert report["test_b"]["starting_equity_usd"] == 10_000.0
    assert set(report["financing_sensitivities"]) == {"0.05", "0.10", "0.15"}
    assert all(transaction["provider_time"].startswith("2022-")
               for transaction in report["test_a"]["transactions"])
    assert all(transaction["provider_time"].startswith("2023-")
               for transaction in report["test_b"]["transactions"])
    assert report["test_a"]["maximum_absolute_notional_usd"] > 10_000.01
    assert report["test_a"]["notional_cap_breached"] is True
    assert report["test_a"]["gates"]["no notional cap breach"] is False
    assert "total net P/L above USD 20 per complete week" in report["test_a"]["gates"]
    assert report["account_margin_evidence"] == {
        "status": "unavailable",
        "classification": "research-only; not evaluated as a pass gate",
    }
    assert all("margin" not in gate.lower() for gate in report["test_a"]["gates"])
    assert report["test_a"]["excluded_incomplete_final_block"] == {
        "days": 1,
        "start_provider_date": "2022-12-31",
        "end_provider_date": "2022-12-31",
    }
    assert report["test_b"]["excluded_incomplete_final_block"]["days"] == 1
    assert report["test_a"]["weeks_above_usd_20_percentage"] == pytest.approx(
        100 * report["test_a"]["weeks_above_usd_20"] / 52
    )
    assert report["test_a"]["profitable_weeks_percentage"] == pytest.approx(
        100 * report["test_a"]["profitable_weeks"] / 52
    )
    assert report["test_a"]["final_exit_provider_time"] == "2022-12-30T00:00:00"
    assert report["test_b"]["final_exit_provider_time"] == "2023-12-30T00:00:00"
    assert report["test_a"]["financing_stopped_at_provider_time"] == (
        report["test_a"]["final_exit_provider_time"]
    )
    assert report["test_a"]["buy_hold_final_exit_provider_time"] == (
        report["test_a"]["final_exit_provider_time"]
    )
    assert report["overall_status"] in {"pass", "fail", "inconclusive"}
    assert report["warning"].endswith("not evidence of future weekly profit.")


def test_weekly_target_applies_literal_adverse_costs_and_calendar_financing():
    report = run_gold_weekly_target_test(
        prepare_daily_gold_history(_synthetic_daily_history()), GoldWeeklyStrategySpec()
    )

    transactions = report["test_a"]["transactions"] + report["test_b"]["transactions"]
    assert {item["side"] for item in transactions} == {"buy", "sell"}
    assert any(item["event"] == "direction_close" for item in transactions)
    assert any(item["event"] == "direction_open" for item in transactions)
    for item in transactions:
        adverse = item["spread_usd"] + item["source_price"] * 0.0002
        expected_fill = (
            item["source_price"] + adverse if item["side"] == "buy"
            else item["source_price"] - adverse
        )
        assert item["fill_price"] == pytest.approx(expected_fill)
        assert item["commission_usd"] == pytest.approx(
            item["quantity_ounces"] * item["fill_price"] * 0.0001
        )

    low = report["financing_sensitivities"]["0.05"]
    primary = report["financing_sensitivities"]["0.10"]
    high = report["financing_sensitivities"]["0.15"]
    for name in ("test_a", "test_b"):
        assert low[name]["total_net_pl_usd"] > primary[name]["total_net_pl_usd"]
        assert primary[name]["total_net_pl_usd"] > high[name]["total_net_pl_usd"]
        assert sum(primary[name]["weekly_pl_usd"]) == pytest.approx(
            primary[name]["total_net_pl_usd"]
        )

    for name in ("test_a", "test_b"):
        low_schedule = [
            (item["provider_time"], item["event"], item["side"], item["quantity_ounces"])
            for item in low[name]["transactions"]
        ]
        high_schedule = [
            (item["provider_time"], item["event"], item["side"], item["quantity_ounces"])
            for item in high[name]["transactions"]
        ]
        assert high_schedule == low_schedule


def test_buy_hold_benchmark_debits_financing_from_each_completed_daily_price():
    prepared = prepare_daily_gold_history(_synthetic_daily_history())
    report = run_gold_weekly_target_test(prepared)
    frame = prepared.frame
    interval = frame[
        (frame.index >= pd.Timestamp("2022-01-01"))
        & (frame.index < pd.Timestamp("2022-12-31"))
    ]
    first, last = interval.iloc[0], interval.iloc[-1]
    entry_fill = first["open"] + 0.2 + first["open"] * 0.0002
    quantity = 10_000 / (entry_fill * 1.0001)
    cash = 10_000 - quantity * entry_fill * 1.0001
    prior_time = interval.index[0]
    prior_close = first["close"]
    for provider_time, row in interval.iloc[1:].iterrows():
        days = (provider_time - prior_time).total_seconds() / 86_400
        cash -= quantity * prior_close * 0.10 * days / 365
        prior_time, prior_close = provider_time, row["close"]
    exit_fill = last["close"] - 0.2 - last["close"] * 0.0002
    cash += quantity * exit_fill * 0.9999

    assert report["test_a"]["buy_hold_net_pl_usd"] == pytest.approx(cash - 10_000)


def test_weekly_target_rejects_prepared_history_mutated_after_hashing():
    prepared = prepare_daily_gold_history(_synthetic_daily_history())
    prepared.frame.loc[prepared.frame.index[-1], "close"] += 100

    with pytest.raises(ValueError, match="changed after preparation"):
        run_gold_weekly_target_test(prepared)


def test_weekly_target_rejects_a_missing_provider_month_before_shifting_lookbacks():
    rows = tuple(
        row for row in _synthetic_daily_history().rows
        if not row["Timestamp"].startswith("2021.06.")
    )
    with pytest.raises(ValueError, match="gap greater than seven calendar days"):
        prepare_daily_gold_history(DailyGoldHistory(
            rows=rows, manifest=({"fixture": "missing-provider-month"},)
        ))


def test_daily_history_rejects_a_gap_long_enough_to_fake_complete_weeks():
    rows = tuple(
        row for row in _synthetic_daily_history().rows
        if not ("2022.06.01" <= row["Timestamp"][:10] <= "2022.06.10")
    )

    with pytest.raises(ValueError, match="gap greater than seven calendar days"):
        prepare_daily_gold_history(DailyGoldHistory(
            rows=rows, manifest=({"fixture": "ten-day-gap"},)
        ))


def test_weekly_target_command_uses_verified_private_cache_and_is_byte_deterministic(tmp_path):
    source, requests = _mock_daily_source()
    cache_path = tmp_path / "daily-cache.json"
    first_report = tmp_path / "weekly-report-1.json"
    second_report = tmp_path / "weekly-report-2.json"

    first = run_gold_weekly_target_command(cache_path, first_report, source=source)
    request_count = len(requests)
    second = run_gold_weekly_target_command(cache_path, second_report, source=source)

    assert first == second
    assert request_count == 37
    assert len(requests) == request_count
    assert first_report.read_bytes() == second_report.read_bytes()
    assert cache_path.stat().st_mode & 0o777 == 0o600
    assert first_report.stat().st_mode & 0o777 == 0o600
    saved = json.loads(first_report.read_text())
    assert saved["report_sha256"] == first["report_sha256"]


def test_gold_weekly_target_cli_writes_bounded_status_without_initializing_trading(tmp_path, monkeypatch, capsys):
    from papertrade.cli import main

    source, _ = _mock_daily_source()
    cache_path = tmp_path / "daily-cache.json"
    run_gold_weekly_target_command(cache_path, tmp_path / "seed-report.json", source=source)
    report_path = tmp_path / "cli-report.json"
    monkeypatch.setattr(sys, "argv", [
        "papertrade", "gold-weekly-target",
        "--cache", str(cache_path),
        "--report", str(report_path),
    ])

    main()

    output = json.loads(capsys.readouterr().out)
    saved = json.loads(report_path.read_text())
    assert output == {
        "report": str(report_path),
        "overall_status": saved["overall_status"],
        "test_a": saved["test_a"]["status"],
        "test_b": saved["test_b"]["status"],
        "warning": saved["warning"],
    }


def test_weekly_target_command_does_not_persist_invalid_fresh_history(tmp_path):
    source, _ = _mock_daily_source(duplicate_first=True)
    cache_path = tmp_path / "invalid-cache.json"

    with pytest.raises(ValueError, match="unique and strictly increasing"):
        run_gold_weekly_target_command(
            cache_path, tmp_path / "never-written-report.json", source=source
        )

    assert not cache_path.exists()


def test_weekly_target_flags_post_cost_leverage_instead_of_hiding_it_by_resizing():
    spec = GoldWeeklyStrategySpec(annual_volatility_target=10.0)

    report = run_gold_weekly_target_test(
        prepare_daily_gold_history(_synthetic_daily_history()), spec
    )

    assert report["test_a"]["notional_cap_breached"] is True
    assert report["test_b"]["notional_cap_breached"] is True
    assert report["test_a"]["gates"]["no notional cap breach"] is False


def test_weekly_target_detects_fixed_notional_cap_breach_on_every_provider_close():
    rows = [dict(row) for row in _synthetic_daily_history().rows]
    for row in rows:
        if row["Timestamp"] == "2022.06.15 00:00:00":
            for field in ("Open", "High", "Low", "Close"):
                row[field] *= 10
            break
    prepared = prepare_daily_gold_history(DailyGoldHistory(
        rows=tuple(rows), manifest=({"fixture": "intramonth-notional-spike"},)
    ))

    report = run_gold_weekly_target_test(prepared)

    assert report["test_a"]["notional_cap_breached"] is True
    assert report["test_a"]["maximum_absolute_notional_usd"] > 10_000
    assert report["test_a"]["gates"]["no notional cap breach"] is False
