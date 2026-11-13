"""Predeclared entry filters using only completed, non-stale higher candles."""

import json
from pathlib import Path

import numpy as np
import pandas as pd

from goldnix_mtf.method import ema

PLAN = json.loads((Path(__file__).parent / "protocol.json").read_text())


def higher_trend(bars, *, minutes, period, slope_bars, warmup):
    seconds = minutes * 60
    frame = bars[["epoch_seconds", "mid_close"]].copy()
    if frame.epoch_seconds.duplicated().any() or (frame.epoch_seconds.diff().dropna() <= 0).any():
        raise ValueError("Unique chronological M1 bars required")
    frame["bucket"] = frame.epoch_seconds // seconds * seconds
    groups = frame.groupby("bucket", sort=True)
    higher = groups.agg(
        close=("mid_close", "last"),
        count=("epoch_seconds", "size"),
        first=("epoch_seconds", "first"),
        last=("epoch_seconds", "last"),
    )
    complete = (
        higher["count"].eq(minutes)
        & higher["first"].eq(higher.index)
        & higher["last"].eq(higher.index + seconds - 60)
    )
    higher = higher.loc[complete]
    indicator = ema(higher["close"], period)
    slope = np.full(len(higher), np.nan)
    if len(higher) > slope_bars:
        slope[slope_bars:] = indicator[slope_bars:] - indicator[:-slope_bars]
    direction = np.select(
        [(higher["close"] > indicator) & (slope > 0), (higher["close"] < indicator) & (slope < 0)], [1, -1], 0
    )
    available = higher.index.to_numpy() + seconds
    decisions = frame.epoch_seconds.to_numpy() + 60
    index = np.searchsorted(available, decisions, side="right") - 1
    if len(higher) == 0:
        return dict(
            direction=np.zeros(len(bars), dtype=int),
            ready=np.zeros(len(bars), dtype=bool),
            available_at=np.full(len(bars), -1),
            complete_bars=0,
        )
    safe = np.maximum(index, 0)
    age = decisions - available[safe]
    ready = (index >= warmup - 1) & (age >= 0) & (age < seconds)
    return dict(
        direction=np.where(ready, direction[safe], 0),
        ready=ready,
        available_at=np.where(index >= 0, available[safe], -1),
        complete_bars=len(higher),
    )


def filter_features(bars, candidate, *, history=None):
    if candidate == "P01":
        return bars
    if candidate not in {"COMMON_P01", *PLAN["candidates"]}:
        raise ValueError("Candidate was not preregistered")
    config = PLAN["trend"]
    combined = bars
    prefix = 0
    if history is not None and len(history):
        if len(bars) == 0 or history.epoch_seconds.max() >= bars.epoch_seconds.min():
            raise ValueError("Warmup context must be strictly earlier than evaluated bars")
        prefix = len(history)
        combined = pd.concat([history, bars], ignore_index=True)
    directions = {}
    for name, minutes, period in [("m15", 15, config["m15_ema_period"]), ("h1", 60, config["h1_ema_period"])]:
        observed = higher_trend(
            combined,
            minutes=minutes,
            period=period,
            slope_bars=config["slope_completed_bars"],
            warmup=config["warmup_complete_bars_each"],
        )
        directions[name] = {key: value[prefix:] for key, value in observed.items() if key != "complete_bars"}
    result = bars.copy()
    raw = bars.direction.to_numpy()
    eligible = directions["m15"]["ready"] & directions["h1"]["ready"]
    if candidate in ("P02_M15", "P04_BOTH", "P05_BOTH_CLOSE"):
        eligible &= raw == directions["m15"]["direction"]
    if candidate in ("P03_H1", "P04_BOTH", "P05_BOTH_CLOSE"):
        eligible &= raw == directions["h1"]["direction"]
    if candidate == "P05_BOTH_CLOSE":
        width = bars.mid_high - bars.mid_low
        location = (bars.mid_close - bars.mid_low) / width.replace(0, np.nan)
        eligible &= np.where(raw == 1, location >= 0.75, location <= 0.25)
    result["direction"] = np.where(eligible, raw, 0)
    return result
