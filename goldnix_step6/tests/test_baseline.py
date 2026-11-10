import numpy as np
import pandas as pd

from goldnix_step6.baseline import run_baseline, sample_schedules, schedule_is_valid
from sim.engine import run_engine


def test_baseline_rejects_overlaps_and_halts_but_resets_next_day():
    # Exit indices, UTC days and realised R for precomputed candidate trades.
    outcomes = pd.DataFrame({
        "entry_index": [1, 2, 4, 6, 25],
        "exit_index": [3, 3, 5, 7, 26],
        "entry_day": [0, 0, 0, 0, 1],
        "exit_day": [0, 0, 0, 0, 1],
        "r_multiple": [-1.2, -1.2, -1.2, 2.0, 2.0],
    })
    assert not schedule_is_valid(outcomes.iloc[[0, 1]], daily_halt_r=-2)
    assert not schedule_is_valid(outcomes.iloc[[0, 2, 3]], daily_halt_r=-2)
    assert schedule_is_valid(outcomes.iloc[[0, 2, 4]], daily_halt_r=-2)


def test_halt_counts_overnight_exit_on_its_realisation_day():
    outcomes = pd.DataFrame({"entry_index": [1, 26, 28, 49], "exit_index": [25, 27, 29, 50],
                             "entry_day": [0, 1, 1, 2], "exit_day": [1, 1, 1, 2],
                             "r_multiple": [-2.1, 2., 2., 2.]})
    assert not schedule_is_valid(outcomes.iloc[[0, 1]], daily_halt_r=-2)
    assert schedule_is_valid(outcomes.iloc[[0, 3]], daily_halt_r=-2)


def test_random_schedules_preserve_counts_are_reproducible_and_obey_the_envelope():
    pool = pd.DataFrame({
        "entry_index": np.arange(1, 41), "exit_index": np.arange(2, 42),
        "entry_day": np.arange(40) // 10, "exit_day": np.arange(40) // 10,
        "r_multiple": [-1.2, 1.9] * 20, "dir": ["BUY", "SELL"] * 20,
    })
    first = sample_schedules(pool, initial_ids=[0, 3, 10, 13], draws=5,
                             sweeps=20, seed=7, daily_halt_r=-2)
    second = sample_schedules(pool, initial_ids=[0, 3, 10, 13], draws=5,
                              sweeps=20, seed=7, daily_halt_r=-2)
    pd.testing.assert_frame_equal(first[0], second[0])
    for _, schedule in first[0].groupby("draw"):
        assert schedule.dir.value_counts().to_dict() == {"BUY": 2, "SELL": 2}
        assert schedule_is_valid(schedule, daily_halt_r=-2)
    assert first[1]["accepted_moves"].gt(0).all()


def test_corrected_baseline_replays_exactly_through_the_strategy_engine():
    bars = pd.DataFrame({
        "timestamp_utc": pd.date_range("2025-01-06", periods=48, freq="h", tz="UTC"),
        "era": "D", "atr": 1.0, "signal": [1, -1] * 24,
        "bid_open": 100.0, "bid_high": 103.0, "bid_low": 97.0, "bid_close": 100.0,
        "ask_open": 100.1, "ask_high": 103.1, "ask_low": 97.1, "ask_close": 100.1,
    })
    config = dict(vol_ceiling_atr=0.3, stop_atr=1., target_atr=2., min_distance_usd=.5,
                  daily_halt_r=-2., friday_no_entry_from_utc="19:00", friday_flat_utc="20:00",
                  holiday_exclusion=True, fill_policy="stop_first",
                  gap_policy="adverse_at_open_favourable_at_target")
    reference = run_engine(bars, config).trades
    trades, diagnostics = run_baseline(bars, config, reference, draws=4, sweeps=10, seed=7)
    for _, draw in trades.groupby("draw"):
        replay = bars.copy()
        replay["signal"] = 0
        for trade in draw.itertuples():
            replay.loc[trade.signal_index, "signal"] = 1 if trade.dir == "BUY" else -1
        actual = run_engine(replay, config).trades
        assert actual.dir.value_counts().to_dict() == reference.dir.value_counts().to_dict()
        assert actual.entry_ts.tolist() == draw.entry_ts.tolist()
        assert actual.exit_ts.tolist() == draw.exit_ts.tolist()
        np.testing.assert_allclose(actual.r_multiple, draw.r_multiple)
