"""Direction-aware random-entry baseline for the V2 H4 regime filter."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from sim.baseline import eligible_signal_indices, run_random_baseline


@dataclass(frozen=True)
class V2BaselineResult:
    trades: pd.DataFrame
    draws: pd.DataFrame
    eligible_bars: dict[str, int]


def _direction_frame(bars: pd.DataFrame, *, buy: bool) -> pd.DataFrame:
    eligible = bars["h4_oscillator"].gt(0) if buy else bars["h4_oscillator"].lt(0)
    frame = bars.copy()
    frame.loc[~eligible, "atr"] = float("nan")
    return frame


def run_v2_random_baseline(
    bars: pd.DataFrame,
    config: dict,
    *,
    longs: int,
    shorts: int,
    draws: int,
    seed: int,
) -> V2BaselineResult:
    """Draw each direction only from bars with matching closed-H4 trend."""
    buy_bars = _direction_frame(bars, buy=True)
    sell_bars = _direction_frame(bars, buy=False)
    buy = run_random_baseline(
        buy_bars,
        config,
        longs=longs,
        shorts=0,
        draws=draws,
        seed=seed,
    )
    sell = run_random_baseline(
        sell_bars,
        config,
        longs=0,
        shorts=shorts,
        draws=draws,
        seed=seed + 1,
    )
    trades = pd.concat([buy.trades, sell.trades], ignore_index=True)
    records = []
    for draw, frame in trades.groupby("draw", sort=True):
        records.append(
            {
                "draw": int(draw),
                "baskets": len(frame),
                "win_rate": float(frame["r_multiple"].gt(0).mean()),
                "mean_r": float(frame["r_multiple"].mean()),
                "long_mean_r": float(
                    frame.loc[frame["dir"].eq("BUY"), "r_multiple"].mean()
                ),
                "short_mean_r": float(
                    frame.loc[frame["dir"].eq("SELL"), "r_multiple"].mean()
                ),
            }
        )
    return V2BaselineResult(
        trades=trades,
        draws=pd.DataFrame.from_records(records),
        eligible_bars={
            "BUY": len(eligible_signal_indices(buy_bars, config)),
            "SELL": len(eligible_signal_indices(sell_bars, config)),
        },
    )

