from datetime import UTC, datetime

import pytest

from goldnix_step9_m5_demo.policy import flatten_deadline, make_run, reconcile, session_window
from goldnix_step9_m5_demo.runner import preset


def test_malaysia_midnight_uses_previous_utc_date():
    window = session_window(datetime(2026, 11, 12, 16, 0, tzinfo=UTC))
    assert window["date"] == "2026-11-13"
    assert window["inside"]
    assert window["end_utc"]-window["start_utc"] == 23400
    assert datetime.fromtimestamp(window["end_utc"], UTC).isoformat() == "2026-11-12T22:30:00+00:00"


@pytest.mark.parametrize("hour,minute,inside", [(15, 59, False), (16, 0, True), (22, 29, True), (22, 30, False)])
def test_start_inclusive_end_exclusive(hour, minute, inside):
    assert session_window(datetime(2026, 11, 12, hour, minute, tzinfo=UTC))["inside"] is inside


def test_naive_clock_refused():
    with pytest.raises(ValueError, match="Timezone-aware"):
        session_window(datetime(2026, 11, 13))


def test_daily_identifiers_stable_and_do_not_reuse_magic_range():
    a = make_run(datetime(2026, 11, 12, 16, tzinfo=UTC))
    b = make_run(datetime(2026, 11, 12, 20, tzinfo=UTC))
    c = make_run(datetime(2026, 11, 13, 16, tzinfo=UTC))
    assert a["run_id"] == b["run_id"]
    assert a["magic_base"] == b["magic_base"]
    assert c["magic_base"] > a["magic_base"]+a["max_trades"]


def test_market_break_preempts_user_deadline_and_friday_close_preempts_both():
    thursday = session_window(datetime(2026, 11, 12, 16, tzinfo=UTC))
    market_close = int(datetime(2026, 11, 12, 21, 58, tzinfo=UTC).timestamp())
    assert flatten_deadline(thursday, market_close) == int(datetime(2026, 11, 12, 21, 56, tzinfo=UTC).timestamp())
    friday = session_window(datetime(2026, 11, 13, 16, tzinfo=UTC))
    assert flatten_deadline(friday, market_close+86400) == int(datetime(2026, 11, 13, 20, tzinfo=UTC).timestamp())


def test_script_preset_uses_epoch_seconds_not_datetime_text(tmp_path):
    class FakeTerminal:
        expected_login = "123"
        build = tmp_path

        def preset(self, filename, values):
            self.values = values

    terminal = FakeTerminal()
    run = make_run(datetime(2026, 11, 12, 16, tzinfo=UTC))
    preset(terminal, run, 0)
    assert terminal.values["StartUTC"] == run["start_utc"]
    assert terminal.values["EndUTC"] == run["end_utc"]
    assert isinstance(terminal.values["StartUTC"], int)


def deal(ticket, entry, *, magic=101, position="1", volume="0.01", profit="0", epoch="100"):
    return {"deal": str(ticket), "entry": str(entry), "magic": str(magic), "position": position,
        "symbol": "XAUUSD.c", "volume": volume, "profit": profit, "commission": "0", "swap": "0", "fee": "0",
        "time_server_epoch": epoch, "price": "100", "reason": "DEAL_REASON_SL"}


def test_reconcile_includes_zero_magic_broker_stop_exit_and_fees():
    entry = deal(1, 0)
    exit_ = deal(2, 1, magic=0, profit="-4.9", epoch="200")
    exit_["commission"] = "-0.1"
    result = reconcile([entry, exit_], 100, 7)
    assert result[0]["pnl_usc"] == -5
    assert result[0]["held_seconds"] == 100


def test_reconcile_handles_confirmed_partial_exit_but_refuses_open_remainder():
    entries = [deal(1, 0), deal(2, 1, magic=0, volume="0.005")]
    with pytest.raises(ValueError, match="remains open"):
        reconcile(entries, 100, 7)
    assert len(reconcile(entries+[deal(3, 1, magic=0, volume="0.005")], 100, 7)) == 1


def test_foreign_activity_not_counted_as_strategy_trades():
    assert reconcile([deal(1, 0, magic=999), deal(2, 1, magic=999)], 100, 7) == []


def test_repeated_entry_magic_is_not_silently_accepted():
    with pytest.raises(ValueError, match="Repeated entry magic"):
        reconcile([deal(1, 0), deal(2, 1), deal(3, 0, position="2"), deal(4, 1, position="2")], 100, 7)
