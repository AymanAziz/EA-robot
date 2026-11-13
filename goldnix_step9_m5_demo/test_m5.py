from datetime import UTC, datetime

import pandas as pd
import pytest

from goldnix_step9_demo.policy import make_run as h1_run
from goldnix_step9_m5_demo.policy import make_run
from goldnix_step9_m5_demo.runner import check_signals, preset, validate_timeframe


def fixture(output, direction=0, *, decision_seconds=300):
    epoch = int(datetime(2026, 11, 12, 8, tzinfo=UTC).timestamp())
    bars = pd.DataFrame({"epoch_seconds": [epoch+i*300 for i in range(100)],
        "bid_open": 100., "bid_high": 100.5, "bid_low": 99.5, "bid_close": 100.,
        "ask_open": 100.1, "ask_high": 100.6, "ask_low": 99.6, "ask_close": 100.1})
    atr = 1.
    if direction:
        close = 101. if direction == 1 else 99.
        extreme = "high" if direction == 1 else "low"
        bars.loc[99, ["bid_close", "ask_close", f"bid_{extreme}", f"ask_{extreme}"]] = [close, close+.1, close, close+.1]
        atr = (13+1.5)/14
    bars.to_csv(output / "m5.csv", index=False)
    signal = {"signal_utc": int(bars.epoch_seconds.iloc[-1]), "decision_utc": int(bars.epoch_seconds.iloc[-1])+decision_seconds,
        "direction": direction, "atr": atr, "distance": 2*atr, "spread": .1, "nominal_usd": (2*atr+.1)*.01}
    pd.DataFrame([signal]).to_csv(output / "signals.csv", index=False)


@pytest.mark.parametrize("direction", [0, 1, -1])
def test_native_m5_closed_bar_fixture_checks_against_python(tmp_path, direction):
    fixture(tmp_path, direction)
    result = check_signals(tmp_path)
    assert result["signals"] == result["matched"] == 1
    assert result["passed"]


def test_forming_m5_bar_cannot_be_used_for_signal(tmp_path):
    fixture(tmp_path, 1, decision_seconds=299)
    with pytest.raises(ValueError, match="differ from Python"):
        check_signals(tmp_path)


@pytest.mark.parametrize("receipt", [{}, {"signal_timeframe": "H1", "bar_seconds": 3600},
    {"signal_timeframe": "M5", "bar_seconds": 3600}])
def test_deployment_rejects_missing_or_inconsistent_native_timeframe(receipt):
    with pytest.raises(ValueError, match="completed M5 bars"):
        validate_timeframe(receipt)


def test_m5_run_is_separate_from_h1_and_preserves_risk_caps():
    now = datetime(2026, 11, 12, 17, tzinfo=UTC)
    previous, current = h1_run(now), make_run(now)
    assert previous["run_id"] != current["run_id"]
    assert current["magic_base"] > previous["magic_base"]+previous["max_trades"]
    assert current["loss_limit_usc"] == previous["loss_limit_usc"] == 10
    assert current["max_trades"] == previous["max_trades"] == 7
    assert current["signal_timeframe"] == "M5" and current["bar_seconds"] == 300


def test_startup_explicitly_selects_m5_chart(tmp_path):
    class Terminal:
        expected_login = "123"
        build = tmp_path

        def preset(self, filename, values):
            self.inputs = values

    terminal = Terminal()
    run = make_run(datetime(2026, 11, 12, 17, tzinfo=UTC))
    config = preset(terminal, run, 0).read_text()
    assert "Period=M5\n" in config
    assert "Script=Goldnix\\M05Session\n" in config
    assert "Enabled=0\n" in config
