"""Independent pandas reference versus shared C++/MQL5 policy and demo exports."""

from io import StringIO
import json
import subprocess

import numpy as np
import pandas as pd

from goldnix_mtf.method import aggregate, ema
from goldnix_research.candidates import prepare_candidate
from .build_source import HERE


def reference(bars):
    bars = bars.rename(columns={"server_seconds": "epoch_seconds"}).copy()
    # Treat declared broker wall-clock grid as a naive timeline, never call it UTC history.
    bars["timestamp_utc"] = pd.to_datetime(bars.epoch_seconds, unit="s", utc=True)
    decision = bars.epoch_seconds.to_numpy() + 300
    h4 = aggregate(bars, 240)
    h4["ema50"] = ema((h4.bid_close + h4.ask_close) / 2, 50)
    slope = h4.ema50 - h4.ema50.shift(3)
    close = (h4.bid_close + h4.ask_close) / 2
    h4["trend"] = np.select([(close > h4.ema50) & (slope > 0), (close < h4.ema50) & (slope < 0)], [1, -1], 0)
    h4_available = pd.DatetimeIndex(h4.available_at).asi8 // 10**9
    ix = np.searchsorted(h4_available, decision, side="right") - 1
    safe = np.maximum(ix, 0)
    ready = (ix >= 99) & (decision >= h4_available[safe]) & (decision < h4_available[safe] + 14400)
    h1 = aggregate(bars, 60)
    h1["epoch_seconds"] = pd.DatetimeIndex(h1.timestamp_utc).asi8 // 10**9
    prepared = prepare_candidate(h1, {"family": "channel", "period": 20})
    high = (h1.bid_high + h1.ask_high) / 2
    low = (h1.bid_low + h1.ask_low) / 2
    hi = high.shift(1).rolling(20).max()
    lo = low.shift(1).rolling(20).min()
    level = np.where(prepared.signal > 0, hi, lo)
    buffer = np.maximum(h1.ask_close - h1.bid_close, 0.1 * prepared.atr)
    hi_ix = np.searchsorted(h1.epoch_seconds.to_numpy() + 3600, decision, side="right") - 1
    hs = np.maximum(hi_ix, 0)
    hr = hi_ix >= 99
    return pd.DataFrame(
        {
            "decision_server": decision,
            "h4_count": ix + 1,
            "h4_available_server": np.where(ix >= 0, h4_available[safe], 0),
            "ema50": np.where(ix >= 49, h4.ema50.to_numpy()[safe], 0),
            "h4_ready": ready,
            "h4_direction": np.where(ready, h4.trend.to_numpy()[safe], 0),
            "h1_open_server": np.where(hi_ix >= 0, h1.epoch_seconds.to_numpy()[hs], 0),
            "h1_ready": hr,
            "direction": np.where(hr, prepared.signal.to_numpy()[hs], 0),
            "atr": np.where(hr, prepared.atr.to_numpy()[hs], 0),
            "level": np.where(hr, level[hs], 0),
            "buffer": np.where(hr, np.asarray(buffer)[hs], 0),
        }
    )


def compare(bars, actual):
    expected = reference(bars)
    if len(actual) != len(expected):
        raise AssertionError("Feature row count mismatch")
    result = {}
    for column in expected:
        values = actual[column].replace({"true": True, "false": False}).to_numpy(dtype=float)
        error = np.max(np.abs(values - expected[column].to_numpy(dtype=float)))
        result[column] = float(error)
        if error > 1e-8:
            raise AssertionError(f"{column}: maximum error {error}")
    return {"rows": len(actual), "passed": True, "maximum_errors": result}


def fixtures():
    output = HERE / "out"
    output.mkdir(exist_ok=True)
    exe = output / "features"
    subprocess.run(["clang++", "-std=c++17", str(HERE / "tests/features.cpp"), "-o", str(exe)], check=True)
    source = pd.read_pickle(HERE.parent / "var/goldnix_mtf_m5/validated.pkl")
    if isinstance(source, dict):
        raise TypeError("Expected validated bar dataframe")
    cols = ["epoch_seconds"] + [
        f"{side}_{kind}" for side in ("bid", "ask") for kind in ("open", "high", "low", "close")
    ]
    frames = []
    for start in (0, 500000):
        frame = (
            source.iloc[start : start + 8500][cols].copy().rename(columns={"epoch_seconds": "server_seconds"})
        )
        frame["ticks"] = 2
        frames.extend([frame, frame.drop(frame.index[[44, 500, 2000]])])
    results = []
    for n, frame in enumerate(frames):
        text = frame.to_csv(index=False, header=False)
        native = subprocess.run([str(exe)], input=text, text=True, capture_output=True, check=True)
        actual = pd.read_csv(StringIO(native.stdout))
        results.append(compare(frame, actual))
        if n == 0:
            (output / "native_fixture.csv").write_text(text)
            frame.to_csv(output / "fixture_bars.csv", index=False)
    (output / "REFERENCE_CHECKS.json").write_text(json.dumps(results, indent=2) + "\n")
    return {"fixtures": len(results), "rows": sum(r["rows"] for r in results), "passed": True}


if __name__ == "__main__":
    print(json.dumps(fixtures()))
