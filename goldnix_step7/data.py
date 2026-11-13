"""Strict holdout validation; no duplicate repair, interpolation, or fitting."""

import gzip
import io
import json
from datetime import timedelta

import numpy as np
import pandas as pd

PRICES = [f"{side}_{kind}" for side in ("bid", "ask") for kind in ("open", "high", "low", "close")]


def read_holdout(payload, *, start, end):
    """Validate native EV JSON/gzip or converted CSV and select the fixed interval."""
    if payload.startswith(b"\x1f\x8b"):
        payload = gzip.decompress(payload)
    if payload.lstrip().startswith(b"["):
        data = pd.DataFrame(json.loads(payload)).rename(columns={
            "ts": "epoch_seconds", "o": "bid_open", "h": "bid_high", "l": "bid_low", "c": "bid_close",
            "ao": "ask_open", "ah": "ask_high", "al": "ask_low", "ac": "ask_close", "v": "provider_volume",
        })
        if "epoch_seconds" not in data:
            raise ValueError("Native EV data must contain ts")
        data["timestamp_utc"] = pd.to_datetime(data.epoch_seconds, unit="s", utc=True)
    else:
        data = pd.read_csv(io.BytesIO(payload))
    required = {"timestamp_utc", "epoch_seconds", "provider_volume", *PRICES}
    if not required.issubset(data.columns) or data.empty:
        raise ValueError("Holdout requires timestamps, bid/ask OHLC, epoch_seconds and provider_volume")
    if not data.timestamp_utc.astype(str).str.contains(r"(?:Z|\+00:00)$").all():
        raise ValueError("Holdout timestamps must have explicit UTC offsets")
    times = pd.to_datetime(data.timestamp_utc, utc=True, errors="raise")
    if (not times.is_unique or not times.is_monotonic_increasing
            or not times.eq(times.dt.floor("h")).all()):
        raise ValueError("Holdout must be unique, increasing, and aligned to UTC H1")
    if not times.dt.year.eq(2026).all():
        raise ValueError("Holdout must contain only unseen 2026 bars; in-sample overlap refused")
    epoch = times.astype("int64") // 1_000_000_000
    if not epoch.eq(pd.to_numeric(data.epoch_seconds, errors="raise")).all():
        raise ValueError("Epoch seconds disagree with UTC timestamps")
    prices = data[PRICES].apply(pd.to_numeric, errors="raise")
    volume = pd.to_numeric(data.provider_volume, errors="raise")
    if (not np.isfinite(prices.to_numpy()).all() or not prices.gt(0).all().all()
            or not np.isfinite(volume.to_numpy()).all() or volume.lt(0).any()):
        raise ValueError("Holdout prices must be finite and positive; volume finite and nonnegative")
    for side in ("bid", "ask"):
        low, high = prices[f"{side}_low"], prices[f"{side}_high"]
        for kind in ("open", "close"):
            if not prices[f"{side}_{kind}"].between(low, high).all():
                raise ValueError("Invalid bid/ask OHLC geometry")
    for kind in ("open", "close"):
        if prices[f"ask_{kind}"].lt(prices[f"bid_{kind}"]).any():
            raise ValueError("Negative open or close spread")
    data[PRICES], data["provider_volume"], data["timestamp_utc"] = prices, volume, times
    selected = data.loc[times.ge(start) & times.lt(end)].copy().reset_index(drop=True)
    if (selected.empty or selected.timestamp_utc.min().to_pydatetime() > start.to_pydatetime() + timedelta(days=7)
            or selected.timestamp_utc.max().to_pydatetime() < end.to_pydatetime() - timedelta(days=7)
            or selected.timestamp_utc.diff().dt.total_seconds().gt(7 * 86400).any()):
        raise ValueError("Holdout does not cover the predeclared interval; no partial-window run")
    return selected
