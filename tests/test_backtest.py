import pandas as pd

from papertrade.backtest import run_backtest
from papertrade.domain import INSTRUMENTS


def price_history(n=100):
    return pd.DataFrame({"open": 100., "high": 101., "low": 99., "close": 100., "volume": 100000.},
                        index=pd.date_range("2025-01-01", periods=n, freq="15min", tz="UTC"))


def execute(frame, probabilities, instrument, **kwargs):
    # Explicit independent forecast input; probability by itself must not trigger entry.
    kwargs.setdefault("expected_returns", pd.Series(.02, index=frame.index))
    return run_backtest(frame, probabilities, instrument, **kwargs)


def test_zero_signals_means_no_trades_and_zero_return():
    frame = price_history()
    report = execute(frame, pd.Series(0.2, index=frame.index), INSTRUMENTS["BTC/USD"])
    assert report["metrics"]["trade_count"] == 0
    assert report["metrics"]["total_return"] == 0


def test_flat_prices_lose_money_after_actual_cost_assumptions():
    frame = price_history()
    report = execute(frame, pd.Series(.9, index=frame.index), INSTRUMENTS["BTC/USD"])
    assert report["metrics"]["total_return"] < 0
    assert report["metrics"]["transaction_costs"] > 0
    assert report["trades"][0]["entry_time"] > report["trades"][0]["signal_time"]


def test_future_close_price_cannot_influence_entry_price():
    frame = price_history()
    signals = pd.Series(.9, index=frame.index)
    original = execute(frame, signals, INSTRUMENTS["BTC/USD"])
    frame.loc[frame.index[52:], "close"] = 100.5
    changed = execute(frame, signals, INSTRUMENTS["BTC/USD"])
    assert original["trades"][0]["entry_price"] == changed["trades"][0]["entry_price"]


def test_a_reproducible_backtest_is_exactly_repeatable():
    frame = price_history()
    probabilities = pd.Series(.9, index=frame.index)
    assert execute(frame, probabilities, INSTRUMENTS["BTC/USD"]) == execute(frame, probabilities, INSTRUMENTS["BTC/USD"])


def test_gap_through_stop_uses_worse_open_instead_of_guaranteed_stop_price():
    frame = price_history()
    frame.loc[frame.index[51], ["open", "high", "low", "close"]] = [80, 81, 79, 80]
    result = execute(frame, pd.Series(.9, index=frame.index), INSTRUMENTS["BTC/USD"])
    assert result["trades"][0]["exit_price"] < 81


def test_unavailable_future_probability_is_not_forward_filled():
    frame = price_history()
    result = execute(frame, pd.Series(.9, index=frame.index[:20]), INSTRUMENTS["BTC/USD"])
    assert result["metrics"]["trade_count"] == 0


def test_incomplete_candle_cannot_be_backtested_as_if_completed():
    frame = price_history()
    result = execute(frame, pd.Series(.9, index=frame.index), INSTRUMENTS["BTC/USD"],
                          now=frame.index[-1].to_pydatetime())
    assert result["equity"][-1]["timestamp"] == frame.index[-2].isoformat()


def test_probability_without_an_expected_net_edge_never_opens_a_position():
    frame = price_history()
    result = run_backtest(frame, pd.Series(.99, index=frame.index), INSTRUMENTS["BTC/USD"])
    assert result["metrics"]["trade_count"] == 0


def test_negative_expected_return_closes_even_while_direction_probability_is_high():
    frame = price_history()
    expected = pd.Series(.02, index=frame.index)
    expected.loc[frame.index[50:]] = -.02
    result = execute(frame, pd.Series(.99, index=frame.index), INSTRUMENTS["BTC/USD"], expected_returns=expected)
    assert len(result["trades"]) == 1
    assert result["trades"][0]["exit_time"] == frame.index[51].isoformat()


def test_risk_exposure_setting_is_used_by_backtest_sizing():
    from papertrade.config import Settings
    frame = price_history()
    result = execute(frame, pd.Series(.99, index=frame.index), INSTRUMENTS["BTC/USD"],
                     settings=Settings(max_instrument_exposure=.01))
    trade = result["trades"][0]
    assert trade["entry_price"] * trade["qty"] <= 100


def test_no_new_position_when_holding_horizon_crosses_known_session_close():
    index = pd.date_range("2025-11-03T14:30:00Z", periods=26, freq="15min").append(
        pd.date_range("2025-11-04T14:30:00Z", periods=26, freq="15min"))
    frame = price_history(52)
    frame.index = index
    result = execute(frame, pd.Series(.99, index=frame.index), INSTRUMENTS["SPY"])
    # Feature warmup completes late in the second session; none of those late
    # decisions has the full validated holding period available before close.
    assert result["metrics"]["trade_count"] == 0
