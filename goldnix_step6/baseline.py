"""Random schedules conditioned on matched counts and the execution envelope."""

from __future__ import annotations

import numpy as np
import pandas as pd

from sim.baseline import _simulate_entry, eligible_signal_indices


def _valid(entries, exits, entry_days, exit_days, returns, halt):
    if np.any(entries[1:] <= exits[:-1]):
        return False
    # Realised R resets at UTC midnight; open trades realise on their exit day.
    cumulative = np.cumsum(returns)
    starts = np.r_[True, exit_days[1:] != exit_days[:-1]]
    group_start = np.maximum.accumulate(np.where(starts, np.arange(len(exits)), 0))
    day_totals = cumulative - np.r_[0.0, cumulative][group_start]
    return not np.any((entry_days[1:] == exit_days[:-1]) & (day_totals[:-1] <= halt))


def schedule_is_valid(outcomes: pd.DataFrame, *, daily_halt_r: float) -> bool:
    """Check a chronological schedule's one-position and UTC daily-halt envelope."""
    if outcomes.empty:
        return True
    ordered = outcomes.sort_values("entry_index")
    return _valid(*(ordered[c].to_numpy() for c in (
        "entry_index", "exit_index", "entry_day", "exit_day", "r_multiple"
    )), daily_halt_r)


def sample_schedules(pool, *, initial_ids, draws, sweeps, seed, daily_halt_r):
    """Independent Metropolis chains, targeting uniform feasible fixed-count schedules.

    Proposals mix single replacement (80%), paired replacement (15%), and a
    complete independent schedule (5%). All are symmetric; the complete draw
    gives positive probability to every feasible schedule, connecting components
    which a single replacement cannot reach. Each draw has its own seeded chain and returns its final
    schedule after the declared burn-in; finite mixing is an approximation,
    reported with midpoint/final means and initial-schedule retention.
    """
    if draws < 1 or sweeps < 2 or len(initial_ids) == 0:
        raise ValueError("draws and trade count must be positive; sweeps must be >= 2")
    pool = pool.reset_index(drop=True)
    initial_ids = np.asarray(initial_ids, dtype=int)
    if not schedule_is_valid(pool.iloc[initial_ids], daily_halt_r=daily_halt_r):
        raise ValueError("initial schedule violates execution envelope")
    entries, exits, entry_days, exit_days, returns = (
        pool[c].to_numpy() for c in
        ("entry_index", "exit_index", "entry_day", "exit_day", "r_multiple")
    )
    dirs = pool["dir"].to_numpy()
    pools = {direction: np.flatnonzero(dirs == direction) for direction in np.unique(dirs)}
    initial_ids = initial_ids[np.argsort(entries[initial_ids])]
    samples, diagnostics = [], []
    moves = sweeps * len(initial_ids)
    for draw, child in enumerate(np.random.SeedSequence(seed).spawn(draws)):
        rng = np.random.default_rng(child)
        selected = initial_ids.copy()
        accepted = 0
        midpoint = None
        for move in range(moves):
            proposal = selected.copy()
            kind = rng.random()
            if kind < 0.05:
                proposal = np.concatenate([
                    rng.choice(candidates, size=int(np.sum(dirs[selected] == direction)), replace=False)
                    for direction, candidates in pools.items()
                ])
            else:
                slots = rng.choice(len(selected), size=min(2 if kind < 0.20 else 1, len(selected)),
                                   replace=False)
                for slot in slots:
                    candidates = pools[dirs[selected[slot]]]
                    proposal[slot] = candidates[rng.integers(len(candidates))]
            proposal = proposal[np.argsort(entries[proposal])]
            if _valid(entries[proposal], exits[proposal], entry_days[proposal],
                      exit_days[proposal], returns[proposal], daily_halt_r):
                selected = proposal
                accepted += 1
            if move == moves // 2 - 1:
                midpoint = float(returns[selected].mean())
        frame = pool.iloc[selected].copy()
        frame["draw"] = draw
        samples.append(frame)
        diagnostics.append({
            "draw": draw, "baskets": len(selected), "accepted_moves": accepted,
            "proposals": moves, "acceptance_rate": accepted / moves,
            "initial_retention": len(set(selected) & set(initial_ids)) / len(selected),
            "midpoint_mean_r": midpoint, "final_mean_r": float(returns[selected].mean()),
        })
    return pd.concat(samples, ignore_index=True), pd.DataFrame(diagnostics)


def run_baseline(bars, config, signal_trades, *, draws, sweeps, seed):
    """Reuse the pinned single-entry fill calculation, then sample feasible schedules."""
    bars = bars.reset_index(drop=True)
    candidates = eligible_signal_indices(bars, config)
    timestamps = pd.DatetimeIndex(bars.timestamp_utc)
    records = []
    for direction in (1, -1):
        if not signal_trades.dir.eq("BUY" if direction == 1 else "SELL").any():
            continue
        for index in candidates:
            if "h4_oscillator" in bars:
                trend = float(bars.iloc[index].h4_oscillator)
                if not np.isfinite(trend) or direction * trend <= 0:
                    continue
            if "cost_eligible" in bars and not bool(bars.iloc[index].cost_eligible):
                continue
            # This frozen function computes only one trade, without sampling or halts.
            # The new schedule sampler applies the missing account-wide envelope.
            record = _simulate_entry(bars, config, int(index), direction)
            record["entry_index"] = int(index + 1)
            record["exit_index"] = int(timestamps.get_indexer([record["exit_ts"]])[0])
            record["entry_day"] = record["entry_ts"].date().toordinal()
            record["exit_day"] = record["exit_ts"].date().toordinal()
            records.append(record)
    pool = pd.DataFrame(records)
    lookup = {(row.entry_ts, row.dir): i for i, row in enumerate(pool.itertuples())}
    initial = [lookup[(row.entry_ts, row.dir)] for row in signal_trades.itertuples()]
    trades, diagnostics = sample_schedules(pool, initial_ids=initial, draws=draws, sweeps=sweeps,
                                           seed=seed, daily_halt_r=float(config["daily_halt_r"]))
    counts = signal_trades.dir.value_counts()
    expected = sum(counts[d] ** 2 / pool.dir.eq(d).sum() for d in counts.index) / len(initial)
    diagnostics["unconstrained_expected_retention"] = expected
    return trades, diagnostics
