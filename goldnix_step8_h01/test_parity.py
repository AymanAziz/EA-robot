import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from goldnix_step8_h01.ea_parity import TICK_DTYPE, diff_trades, quote_bars, reference
from goldnix_step8_h01.audit_receipt import audit


def test_quote_extrema_preserve_frozen_midpoint_definition():
    ticks = np.array([(1000, 100., 110.), (2000, 101., 102.)], dtype=TICK_DTYPE)
    bar = quote_bars(ticks, 3600, 0).iloc[0]
    assert (bar.bid_high + bar.ask_high) / 2 == 105.5
    assert ((ticks["bid"] + ticks["ask"]) / 2).max() == 105.


def trades(entry="2026-11-09T01:00Z", exit_="2026-11-09T01:05Z", direction="BUY", reason="stop"):
    return pd.DataFrame([{"entry_ts": entry, "exit_ts": exit_, "dir": direction,
                          "exit_reason": reason, "entry": 100., "exit": 99.}])


def test_empty_lists_do_not_pass():
    empty = trades().iloc[:0]
    result, _ = diff_trades(empty, empty)
    assert result["status"] == "INSUFFICIENT_DATA"
    assert result["match_ratio"] is None


def test_intrabar_seconds_match_but_different_exit_bar_does_not():
    result, _ = diff_trades(trades(exit_="2026-11-09T01:09:59Z"), trades())
    assert result["status"] == "PASS"
    result, _ = diff_trades(trades(exit_="2026-11-09T01:10:00Z"), trades())
    assert result["status"] == "FAIL"


def test_wrong_direction_and_unmatched_entries_count_against_parity():
    result, rows = diff_trades(trades(direction="SELL"), trades())
    assert result["comparison_rows"] == 2
    assert result["matching_trades"] == 0
    assert len(rows.loc[~rows.match]) == 2


def test_stop_and_gap_stop_are_not_silently_equated():
    result, _ = diff_trades(trades(reason="gap_stop"), trades())
    assert result["status"] == "FAIL"


def test_duplicate_entries_refused():
    with pytest.raises(ValueError, match="Duplicate"):
        diff_trades(pd.concat([trades(), trades()]), trades())


@pytest.mark.parametrize("entry,exit_", [(-7200, 1708097798), (1707991200, -7200),
                                        (1707991200, 1707991199)])
def test_native_timestamp_audit_rejects_missing_deal_fields(entry, exit_):
    frame = pd.DataFrame([{"entry_utc": entry, "exit_utc": exit_}])
    operation = {"TradeFromUTC": "2024.02.01 00:00:00", "WindowEndUTC": "2024.02.29 22:00:00"}
    with pytest.raises(ValueError, match="Native deal timestamps"):
        audit(frame, operation)


def test_native_timestamp_audit_accepts_independent_journal_times():
    operation = {"TradeFromUTC": "2024.02.01 00:00:00", "WindowEndUTC": "2024.02.29 22:00:00"}
    frame = pd.DataFrame([{"entry_utc": 1707991200, "exit_utc": 1708097798}])
    assert audit(frame, operation) == {"trade_timestamps_valid": True, "native_trades": 1}


@pytest.mark.parametrize("direction", [1, -1])
def test_frozen_reference_enters_both_directions_on_next_bar(direction):
    decision = json.loads((Path(__file__).parent / "decision.json").read_text())
    start = pd.Timestamp("2026-11-02T00:00Z")
    decision["operational_inputs"]["TradeFromUTC"] = "2026.11.06 04:00:00"
    rows = []
    for hour in range(115):
        bids = [100., 100.05, 99.95, 100.]
        if hour == 110:
            bids[-1] = 101.
        if hour == 111:
            bids = [101., 103., 100.95, 101.]
        for second, bid in zip((0, 60, 120, 299), bids):
            bid = 100. + direction*(bid-100.)
            server_msc = (start.value // 10**9 + hour*3600 + second + 7200)*1000
            rows.append((server_msc, bid, bid+.02))
    expected, _, _, _ = reference(np.array(rows, dtype=TICK_DTYPE), decision)
    assert len(expected) == 1
    trade = expected.iloc[0]
    assert trade.dir == ("BUY" if direction == 1 else "SELL")
    assert pd.Timestamp(trade.entry_ts).value == start.value + 111*3600*10**9
    assert trade.exit_reason == "target"
    assert trade.distance == .5
