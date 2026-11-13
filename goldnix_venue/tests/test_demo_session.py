from pathlib import Path
import copy
import json

import pytest

from goldnix_venue.demo_session import reconcile_history, rows, save_report, validate_account


def account(**changes):
    return {"server": "JustMarkets-Demo6", "currency": "USC", "account_trade_mode": "0",
            "identity_matches": "1", "connected": "1", "history_selected": "1",
            "positions": "0", "orders": "0", "terminal_trade_allowed": "0", "mql_trade_allowed": "0",
            **changes}


@pytest.fixture
def broker_history():
    path = Path(__file__).parents[1] / "out/demo_batch_M1B_20261112T091641Z/post_restart_history.csv"
    return rows(path)


def test_reconciles_every_broker_exit_including_the_disconnect_stop_loss(broker_history):
    trades = reconcile_history(broker_history, 1794475001000, 30)
    assert len(trades) == 12
    assert sum(trade["pnl_usc"] for trade in trades) == pytest.approx(-.26)
    assert trades[-1]["held_seconds"] == 382
    assert trades[-1]["exit_deal"] == 113998808
    assert trades[-1]["exit_reason"] == "DEAL_REASON_SL"


def test_exit_with_broker_magic_zero_is_still_counted_and_duplicate_rows_are_idempotent(broker_history):
    history = copy.deepcopy(broker_history)
    for row in history:
        if row["entry"] == "1":
            row["magic"] = "0"
    trades = reconcile_history(history + history, 1794475001000, 30)
    assert len(trades) == 12
    assert trades[-1]["pnl_usc"] == -1.38


def test_unclosed_trade_cannot_be_reported_complete(broker_history):
    history = [row for row in broker_history if row["deal"] != "113998808"]
    with pytest.raises(ValueError, match="fully closed"):
        reconcile_history(history, 1794475001000, 30)


@pytest.mark.parametrize("changes", [
    {"account_trade_mode": "2"}, {"identity_matches": "0"}, {"connected": "0"},
    {"server": "JustMarkets-Live"}, {"currency": "USD"}, {"positions": "1"},
    {"terminal_trade_allowed": "1"}, {"mql_trade_allowed": "1"},
])
def test_completion_rejects_wrong_account_offline_open_or_enabled_state(changes):
    with pytest.raises(ValueError):
        validate_account(account(**changes), flat=True, disabled=True)


def test_report_matches_broker_history_and_preserves_cent_units(tmp_path, broker_history):
    run = {"run_id": "demo_test", "magic_base": 1794475001000, "max_trades": 30}
    snapshot = account(captured_utc_epoch="1794482386", net_pnl_usc="-0.26", balance_usc="1999.99",
                       matching_positions="12", entry_deals="12", exit_deals="12")
    save_report(run, tmp_path, snapshot, broker_history, "connection_interruption", "2000.25")
    receipt = json.loads((tmp_path / "RECEIPT.json").read_text())
    assert receipt["net_pnl_usd"] == -.0026
    assert receipt["wins"] == 7
    assert receipt["losses"] == 5
    assert receipt["automation_enabled"] is False
    assert receipt["step6_approved"] is False


def test_balance_mismatch_leaves_no_success_receipt(tmp_path, broker_history):
    run = {"run_id": "demo_test", "magic_base": 1794475001000, "max_trades": 30}
    snapshot = account(captured_utc_epoch="1794482386", net_pnl_usc="-0.26", balance_usc="2009.99",
                       matching_positions="12", entry_deals="12", exit_deals="12")
    with pytest.raises(ValueError, match="Balance changed"):
        save_report(run, tmp_path, snapshot, broker_history, "complete", "2000.25")
    assert not (tmp_path / "RECEIPT.json").exists()
