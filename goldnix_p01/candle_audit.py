"""Audit paired public candles without inventing quotes in placeholder minutes."""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .download_candles import CACHE, decode


def pair(bid_payload, ask_payload, day, *, preceding=None):
    bid, ask = decode(bid_payload), decode(ask_payload)
    if not np.array_equal(bid["second"], ask["second"]):
        raise ValueError("Bid/Ask minute timestamps differ")
    result = pd.DataFrame(
        {"epoch_seconds": int(pd.Timestamp(day, tz="UTC").timestamp()) + bid["second"].astype("int64")}
    )
    for side, data in (("bid", bid), ("ask", ask)):
        for key in ("open", "high", "low", "close"):
            result[f"{side}_{key}"] = data[key].astype(float) / 1000
        result[f"{side}_volume"] = data["volume"]
    if any((result["ask_" + k] < result["bid_" + k]).any() for k in ("open", "high", "low", "close")):
        raise ValueError("Crossed Bid/Ask candle geometry")
    zero = (result.bid_volume == 0) | (result.ask_volume == 0)
    placeholder = (result.bid_volume == 0) & (result.ask_volume == 0)
    for side in ("bid", "ask"):
        previous = result[side + "_close"].shift(1)
        if len(previous) and preceding is not None:
            previous.iloc[0] = preceding[side]
        for key in ("open", "high", "low", "close"):
            placeholder &= result[side + "_" + key].eq(previous)
    result["classification"] = np.where(
        placeholder, "placeholder", np.where(zero, "unexplained_zero_volume", "observed")
    )
    if (result.loc[~zero, ["bid_low", "ask_low"]] <= 0).any().any():
        raise ValueError("Observed nonpositive candle price")
    return result


def audit(cache=CACHE):
    cache = Path(cache)
    dates = sorted({p.name[:10] for p in cache.glob("*_BID.json")})
    rows, preceding, previous_day = [], None, None
    hashes = {}
    for day in dates:
        if day >= "2026-01-01":
            raise ValueError("Holdout payload in in-sample cache")
        paths = [cache / f"{day}_{side}.bi5" for side in ("BID", "ASK")]
        if not all(p.exists() and p.with_suffix(".json").exists() for p in paths):
            rows.append(dict(date=day, status="missing_pair"))
            continue
        for path in paths:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if digest != json.loads(path.with_suffix(".json").read_text())["sha256"]:
                raise ValueError("Archive hash mismatch: " + path.name)
            hashes[path.name] = digest
        stamp = pd.Timestamp(day)
        if previous_day is None or (stamp - previous_day).days != 1:
            preceding = None
        frame = pair(*(p.read_bytes() for p in paths), day, preceding=preceding)
        counts = frame.classification.value_counts().to_dict()
        rows.append(dict(date=day, status="decoded", rows=len(frame), **counts))
        if len(frame):
            preceding = {s: float(frame.iloc[-1][s + "_close"]) for s in ("bid", "ask")}
        previous_day = stamp
    summary = dict(
        cached_calendar_days=len(dates),
        paired_days=sum(r["status"] == "decoded" for r in rows),
        first_date=dates[0] if dates else None,
        last_date=dates[-1] if dates else None,
        classifications={
            k: sum(r.get(k, 0) for r in rows) for k in ("observed", "placeholder", "unexplained_zero_volume")
        },
        four_era_coverage_passed=False,
        intraminute_ticks_available=False,
        qualification="PARTIAL: M1 candles alone cannot qualify one-second profit management",
        archive_hashes=hashes,
        days=rows,
    )
    (cache / "AUDIT.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps({k: v for k, v in summary.items() if k not in ("archive_hashes", "days")}))
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=CACHE)
    audit(parser.parse_args().cache)
