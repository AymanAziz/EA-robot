from __future__ import annotations

from datetime import date
import hashlib
import json
import math
import sys

import httpx
import pandas as pd
import pytest

from papertrade.gold_research import (
    AlgoSpecialGoldHistory,
    GoldHistory,
    gold_double_test_report,
    prepare_gold_history,
    run_gold_double_test,
)


def test_prepare_gold_history_preserves_provider_clock_and_segments_gaps():
    history = GoldHistory(
        rows=(
            {"Timestamp": "2026.10.01 00:00:00", "Open": 4156.124, "High": 4157.0,
             "Low": 4155.0, "Close": 4156.5, "TickVolume": 2247, "Spread": 240},
            {"Timestamp": "2026.10.01 00:15:00", "Open": 4156.5, "High": 4158.0,
             "Low": 4156.0, "Close": 4157.0, "TickVolume": 1200, "Spread": 180},
            {"Timestamp": "2026.10.01 01:00:00", "Open": 4157.0, "High": 4159.0,
             "Low": 4156.5, "Close": 4158.0, "TickVolume": 1600, "Spread": 200},
        ),
        manifest=({"request_start": "2026-10-01", "request_end": "2026-10-01", "rows": 3},),
    )

    prepared = prepare_gold_history(history)

    assert prepared.source_id == "algospecial_xauusd_m15_preview"
    assert prepared.frame.index.name == "provider_time"
    assert prepared.frame.index.tz is None
    assert prepared.frame.index.tolist() == [
        pd.Timestamp("2026-10-01 00:00:00"),
        pd.Timestamp("2026-10-01 00:15:00"),
        pd.Timestamp("2026-10-01 01:00:00"),
    ]
    assert prepared.frame["segment"].tolist() == [0, 0, 1]
    assert prepared.frame["spread_usd"].tolist() == [0.24, 0.18, 0.2]
    assert prepared.manifest == history.manifest
    assert len(prepared.data_sha256) == 64


def test_prepare_gold_history_rejects_duplicate_provider_times():
    row = {"Timestamp": "2026.10.01 00:00:00", "Open": 4156.0, "High": 4157.0,
           "Low": 4155.0, "Close": 4156.5, "TickVolume": 100, "Spread": 200}
    history = GoldHistory(rows=(row, dict(row)), manifest=())

    with pytest.raises(ValueError, match="unique and strictly increasing"):
        prepare_gold_history(history)


def test_prepare_gold_history_rejects_unordered_provider_times():
    rows = (
        {"Timestamp": "2026.10.01 00:15:00", "Open": 4156.0, "High": 4157.0,
         "Low": 4155.0, "Close": 4156.5, "TickVolume": 100, "Spread": 200},
        {"Timestamp": "2026.10.01 00:00:00", "Open": 4156.0, "High": 4157.0,
         "Low": 4155.0, "Close": 4156.5, "TickVolume": 100, "Spread": 200},
    )

    with pytest.raises(ValueError, match="unique and strictly increasing"):
        prepare_gold_history(GoldHistory(rows=rows, manifest=()))


def test_prepare_gold_history_rejects_impossible_ohlc():
    row = {"Timestamp": "2026.10.01 00:00:00", "Open": 4156.0, "High": 4155.0,
           "Low": 4154.0, "Close": 4156.5, "TickVolume": 100, "Spread": 200}

    with pytest.raises(ValueError, match="OHLC invariants"):
        prepare_gold_history(GoldHistory(rows=(row,), manifest=()))


def test_prepare_gold_history_rejects_nonpositive_prices():
    row = {"Timestamp": "2026.10.01 00:00:00", "Open": 0, "High": 4157.0,
           "Low": 0, "Close": 4156.5, "TickVolume": 100, "Spread": 200}

    with pytest.raises(ValueError, match="finite positive prices"):
        prepare_gold_history(GoldHistory(rows=(row,), manifest=()))


def test_prepare_gold_history_rejects_negative_spread_but_hashes_missing_spread():
    row = {"Timestamp": "2026.10.01 00:00:00", "Open": 4156.0, "High": 4157.0,
           "Low": 4155.0, "Close": 4156.5, "TickVolume": 100, "Spread": -1}

    with pytest.raises(ValueError, match="finite nonnegative spread"):
        prepare_gold_history(GoldHistory(rows=(row,), manifest=()))

    row["Spread"] = None
    prepared = prepare_gold_history(GoldHistory(rows=(row,), manifest=()))
    assert pd.isna(prepared.frame["spread_usd"].iloc[0])
    assert len(prepared.data_sha256) == 64


def test_run_gold_double_test_rejects_history_mutated_after_preparation():
    prepared = prepare_gold_history(_synthetic_gold_history())
    prepared.frame.loc[prepared.frame.index[-1], "close"] += 1

    with pytest.raises(ValueError, match="changed after preparation"):
        run_gold_double_test(prepared)


def test_algospecial_fetch_uses_inclusive_twenty_day_chunks_and_records_provenance():
    requests = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        start = request.url.params["from"]
        row = {"Timestamp": f"{start.replace('-', '.')} 00:00:00", "Open": 2000.0,
               "High": 2001.0, "Low": 1999.0, "Close": 2000.5, "TickVolume": 10, "Spread": 200}
        return httpx.Response(200, json={"symbol": "XAUUSD", "timeframe": "M15",
                                         "from": start, "to": request.url.params["to"],
                                         "rows": 1, "data": [row]},
                              headers={"X-RateLimit-Limit": "60", "X-RateLimit-Remaining": "59"})

    client = httpx.Client(transport=httpx.MockTransport(respond))

    history = AlgoSpecialGoldHistory(client=client).fetch(date(2026, 1, 1), date(2026, 1, 25))

    assert [(request.url.params["from"], request.url.params["to"]) for request in requests] == [
        ("2026-01-01", "2026-01-20"),
        ("2026-01-21", "2026-01-25"),
    ]
    assert len(history.rows) == 2
    assert [entry["returned_rows"] for entry in history.manifest] == [1, 1]
    assert all(len(entry["response_sha256"]) == 64 for entry in history.manifest)
    assert all(entry["provider_clock"] == "broker server time; timezone unknown" for entry in history.manifest)


def test_algospecial_fetch_waits_for_retry_after_and_retries_a_429_once():
    attempts = 0
    sleeps = []

    def respond(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(429, headers={"Retry-After": "3"}, json={"error": "rate limited"})
        return httpx.Response(200, json={"symbol": "XAUUSD", "timeframe": "M15",
                                         "from": "2026-01-01", "to": "2026-01-01",
                                         "rows": 0, "data": []})

    client = httpx.Client(transport=httpx.MockTransport(respond))

    history = AlgoSpecialGoldHistory(client=client, sleeper=sleeps.append).fetch(
        date(2026, 1, 1), date(2026, 1, 1)
    )

    assert history.rows == ()
    assert attempts == 2
    assert sleeps == [3]


def test_algospecial_fetch_rejects_payload_metadata_that_does_not_match_request():
    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"symbol": "EURUSD", "timeframe": "M15",
                                         "from": "2026-01-01", "to": "2026-01-01",
                                         "rows": 0, "data": []})

    client = httpx.Client(transport=httpx.MockTransport(respond))

    with pytest.raises(ValueError, match="AlgoSpecial response metadata"):
        AlgoSpecialGoldHistory(client=client).fetch(date(2026, 1, 1), date(2026, 1, 1))


def test_algospecial_fetch_rejects_row_outside_requested_chunk():
    row = {"Timestamp": "2026.01.02 00:00:00", "Open": 2000.0, "High": 2001.0,
           "Low": 1999.0, "Close": 2000.5, "TickVolume": 10, "Spread": 200}

    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"symbol": "XAUUSD", "timeframe": "M15",
                                         "from": "2026-01-01", "to": "2026-01-01",
                                         "rows": 1, "data": [row]})

    client = httpx.Client(transport=httpx.MockTransport(respond))

    with pytest.raises(ValueError, match="outside its requested chunk"):
        AlgoSpecialGoldHistory(client=client).fetch(date(2026, 1, 1), date(2026, 1, 1))


def test_algospecial_fetch_returns_immutable_rows_and_provenance():
    row = {"Timestamp": "2026.01.01 00:00:00", "Open": 2000.0, "High": 2001.0,
           "Low": 1999.0, "Close": 2000.5, "TickVolume": 10, "Spread": 200}

    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"symbol": "XAUUSD", "timeframe": "M15",
                                         "from": "2026-01-01", "to": "2026-01-01",
                                         "rows": 1, "data": [row]})

    client = httpx.Client(transport=httpx.MockTransport(respond))
    history = AlgoSpecialGoldHistory(client=client).fetch(date(2026, 1, 1), date(2026, 1, 1))

    with pytest.raises(TypeError):
        history.rows[0]["Open"] = 1.0
    with pytest.raises(TypeError):
        history.manifest[0]["request_start"] = "changed"


def test_gold_double_test_report_uses_wilson_bound_and_requires_two_hundred_trades():
    net_pl = [1.0] * 60 + [-1.0] * 40
    replay = {
        "trades": tuple({"net_pl": value} for value in net_pl),
        "equity": tuple(10_000 + sum(net_pl[:index]) for index in range(len(net_pl) + 1)),
        "rule_total_return": -0.01,
        "buy_hold_total_return": -0.01,
        "partition_sha256": "a" * 64,
    }

    report = gold_double_test_report(
        replay,
        replay,
        frozen={"model_sha256": "b" * 64, "threshold_sha256": "c" * 64, "threshold": 0.6},
    )

    assert report["test_a"]["win_rate"] == pytest.approx(0.6)
    assert report["test_a"]["wilson_95_lower"] == pytest.approx(0.5020025868)
    assert report["test_a"]["status"] == "inconclusive"
    assert report["overall_status"] == "inconclusive"


def test_gold_double_test_report_fails_a_high_win_rate_that_loses_after_costs():
    net_pl = [0.1] * 120 + [-1.0] * 80
    replay = {
        "trades": tuple({"net_pl": value} for value in net_pl),
        "equity": tuple(10_000 + sum(net_pl[:index]) for index in range(len(net_pl) + 1)),
        "rule_total_return": -0.02,
        "buy_hold_total_return": -0.02,
        "partition_sha256": "d" * 64,
    }

    report = gold_double_test_report(
        replay,
        replay,
        frozen={"model_sha256": "b" * 64, "threshold_sha256": "c" * 64, "threshold": 0.6},
    )

    assert report["test_a"]["win_rate"] == pytest.approx(0.6)
    assert report["test_a"]["after_cost_net_pl"] == pytest.approx(-68.0)
    assert report["test_a"]["gates"]["positive after-cost return"] is False
    assert report["test_a"]["status"] == "fail"
    assert report["overall_status"] == "fail"


def test_gold_double_test_report_requires_every_gate_in_each_test_without_pooling():
    profitable = [1.0] * 130 + [-0.1] * 70
    losing = [1.0] * 130 + [-3.0] * 70

    def replay(values, digest):
        return {
            "trades": tuple({"net_pl": value} for value in values),
            "equity": tuple(10_000 + sum(values[:index]) for index in range(len(values) + 1)),
            "rule_total_return": 0.001,
            "buy_hold_total_return": 0.002,
            "partition_sha256": digest * 64,
        }

    report = gold_double_test_report(
        replay(profitable, "e"),
        replay(losing, "f"),
        frozen={"model_sha256": "b" * 64, "threshold_sha256": "c" * 64, "threshold": 0.6},
    )

    assert report["test_a"]["status"] == "pass"
    assert report["test_b"]["status"] == "fail"
    assert report["overall_status"] == "fail"
    assert set(report["test_a"]["gates"]) == {
        "point win rate above 50%",
        "Wilson 95% lower bound above 50%",
        "positive after-cost return",
        "profit factor above one",
        "provider-bar Sharpe above zero",
        "maximum drawdown no worse than -10%",
        "positive bootstrap lower mean trade P/L",
        "outperform frozen rule",
        "outperform capped buy-and-hold",
    }


def _synthetic_gold_history(count: int = 1_200, *, gap_after: int | None = None) -> GoldHistory:
    times = list(pd.date_range("2024-01-01", periods=count, freq="15min"))
    if gap_after is not None:
        times = [value if index <= gap_after else value + pd.to_timedelta(2, unit="h")
                 for index, value in enumerate(times)]
    rows = []
    for index, provider_time in enumerate(times):
        center = 2_000 + 5 * math.sin(index / 7) + 2 * math.sin(index / 31) + index * 0.002
        opening = center + 0.4 * math.sin(index / 3)
        closing = center + 0.4 * math.sin((index + 1) / 3)
        rows.append({
            "Timestamp": provider_time.strftime("%Y.%m.%d %H:%M:%S"),
            "Open": round(opening, 3),
            "High": round(max(opening, closing) + 0.8, 3),
            "Low": round(min(opening, closing) - 0.8, 3),
            "Close": round(closing, 3),
            "TickVolume": 1_000 + index % 200,
            "Spread": 200 + index % 20,
        })
    return GoldHistory(rows=tuple(rows), manifest=({"fixture": "deterministic-price-only"},))


def test_run_gold_double_test_freezes_costs_and_excludes_unknown_clock_features():
    prepared = prepare_gold_history(_synthetic_gold_history())

    report = run_gold_double_test(prepared)

    forbidden = {"hour_sin", "hour_cos", "weekday_sin", "weekday_cos", "london_session", "ny_session"}
    assert forbidden.isdisjoint(report["feature_names"])
    assert report["cost_policy"] == {
        "spread": "one full observed spread at entry and exit",
        "zero_spread_fallback": "development-only nonzero p99 (higher)",
        "slippage_bps_per_side": 2.0,
        "commission_bps_per_side": 1.0,
    }
    assert len(report["frozen"]["model_sha256"]) == 64
    assert len(report["frozen"]["threshold_sha256"]) == 64
    assert pd.Timestamp(report["partitions"]["test_b"]["start_provider_time"]) > (
        pd.Timestamp(report["partitions"]["test_a"]["end_provider_time"]) + pd.to_timedelta(75, unit="min")
    )
    assert report["test_a"]["status"] == "inconclusive"
    assert report["test_b"]["status"] == "inconclusive"


def test_run_gold_double_test_audits_literal_costs_and_never_trades_across_gaps():
    prepared = prepare_gold_history(_synthetic_gold_history(gap_after=1_000))

    report = run_gold_double_test(prepared)

    closed_trades = report["test_a"]["closed_trades"] + report["test_b"]["closed_trades"]
    assert closed_trades
    assert report["test_a"]["equity_observations"] > report["test_a"]["trade_count"] + 1
    assert report["test_b"]["equity_observations"] > report["test_b"]["trade_count"] + 1
    for trade in closed_trades:
        assert pd.Timestamp(trade["exit_provider_time"]) - pd.Timestamp(
            trade["signal_provider_time"]
        ) == pd.to_timedelta(75, unit="min")
        expected_entry = trade["entry_open"] + trade["entry_spread_usd"] + trade["entry_open"] * 0.0002
        expected_exit = trade["exit_open"] - trade["exit_spread_usd"] - trade["exit_open"] * 0.0002
        expected_commission = (expected_entry + expected_exit) * 0.0001
        assert trade["entry_fill"] == pytest.approx(expected_entry)
        assert trade["exit_fill"] == pytest.approx(expected_exit)
        assert trade["net_pl"] == pytest.approx(expected_exit - expected_entry - expected_commission)


def test_run_gold_double_test_is_deterministic_and_test_changes_cannot_change_frozen_choices():
    history = _synthetic_gold_history()
    prepared = prepare_gold_history(history)

    first = run_gold_double_test(prepared)
    repeated = run_gold_double_test(prepared)
    changed_rows = [dict(row) for row in history.rows]
    for row in changed_rows[1_000:]:
        for column in ("Open", "High", "Low", "Close"):
            row[column] += 20
        row["Spread"] = 0
    changed = run_gold_double_test(prepare_gold_history(GoldHistory(
        rows=tuple(changed_rows), manifest=history.manifest
    )))

    assert repeated == first
    assert changed["frozen"]["model_sha256"] == first["frozen"]["model_sha256"]
    assert changed["frozen"]["threshold_sha256"] == first["frozen"]["threshold_sha256"]
    assert changed["frozen"]["development_spread_p99_usd"] == first["frozen"]["development_spread_p99_usd"]
    assert changed["partitions"]["test_b"]["sha256"] != first["partitions"]["test_b"]["sha256"]


def test_gold_double_test_cli_uses_private_cache_and_writes_report(tmp_path, monkeypatch, capsys):
    from papertrade.cli import main

    history = _synthetic_gold_history(800)
    cache_path = tmp_path / "gold-cache.json"
    report_path = tmp_path / "gold-report.json"
    rows = [dict(row) for row in history.rows]
    payload = {"symbol": "XAUUSD", "timeframe": "M15", "from": "2024-01-01",
               "to": "2024-01-09", "rows": len(rows), "data": rows}
    cache_path.write_text(json.dumps({
        "source_id": "algospecial_xauusd_m15_preview",
        "start": "2024-01-01",
        "end": "2024-01-09",
        "rows": rows,
        "manifest": [{
            "endpoint": "https://www.algospecial.com/api/ohlc.php",
            "request_start": "2024-01-01",
            "request_end": "2024-01-09",
            "symbol": "XAUUSD",
            "timeframe": "M15",
            "provider_clock": "broker server time; timezone unknown",
            "returned_rows": len(rows),
            "response_sha256": hashlib.sha256(json.dumps(
                payload, sort_keys=True, separators=(",", ":"), allow_nan=False
            ).encode()).hexdigest(),
        }],
    }))
    monkeypatch.setattr(sys, "argv", [
        "papertrade", "gold-double-test",
        "--start", "2024-01-01",
        "--end", "2024-01-09",
        "--cache", str(cache_path),
        "--report", str(report_path),
    ])

    main()

    output = json.loads(capsys.readouterr().out)
    saved = json.loads(report_path.read_text())
    assert output["report"] == str(report_path)
    assert output["overall_status"] == saved["overall_status"]
    assert saved["warning"].endswith("not evidence of future profitability.")


def test_gold_double_test_cli_rejects_cache_without_exact_chunk_provenance(tmp_path, monkeypatch):
    from papertrade.cli import main

    history = _synthetic_gold_history(800)
    cache_path = tmp_path / "incomplete-cache.json"
    cache_path.write_text(json.dumps({
        "source_id": "algospecial_xauusd_m15_preview",
        "start": "2024-01-01",
        "end": "2024-01-09",
        "rows": [dict(row) for row in history.rows],
        "manifest": [],
    }))
    monkeypatch.setattr(sys, "argv", [
        "papertrade", "gold-double-test",
        "--start", "2024-01-01", "--end", "2024-01-09",
        "--cache", str(cache_path), "--report", str(tmp_path / "report.json"),
    ])

    with pytest.raises(ValueError, match="cache manifest coverage"):
        main()
