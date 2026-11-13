"""Public closed-year M5 retrieval and conservative quote validation."""

import gzip
import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "var/goldnix_mtf_m5"
RENAME = {"ts": "epoch_seconds", "o": "bid_open", "h": "bid_high", "l": "bid_low",
          "c": "bid_close", "ao": "ask_open", "ah": "ask_high", "al": "ask_low",
          "ac": "ask_close", "v": "provider_volume"}
PRICES = [f"{s}_{k}" for s in ("bid", "ask") for k in ("open", "high", "low", "close")]


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def validate(frame, year):
    """Bad quote rows are quarantined; time ordering/grid errors abort."""
    frame = frame.rename(columns=RENAME)
    if not set(RENAME.values()).issubset(frame.columns):
        raise ValueError("Unexpected publisher schema")
    stamp = frame.epoch_seconds.to_numpy()
    if (np.diff(stamp) <= 0).any() or (stamp % 300 != 0).any():
        raise ValueError("Duplicate, unordered, or off-grid timestamps")
    frame["timestamp_utc"] = pd.to_datetime(stamp, unit="s", utc=True)
    if not frame.timestamp_utc.dt.year.eq(year).all():
        raise ValueError("Annual archive contains another year")
    good = np.isfinite(frame[PRICES]).all(axis=1) & frame[PRICES].gt(0).all(axis=1)
    for side in ("bid", "ask"):
        good &= (frame[f"{side}_high"].ge(frame[[f"{side}_open", f"{side}_close"]].max(axis=1))
                 & frame[f"{side}_low"].le(frame[[f"{side}_open", f"{side}_close"]].min(axis=1))
                 & frame[f"{side}_high"].ge(frame[f"{side}_low"]))
    good &= frame.ask_open.ge(frame.bid_open) & frame.ask_close.ge(frame.bid_close)
    return frame.loc[good].copy(), frame.loc[~good].copy()


def retrieve(protocol):
    """Only publicly advertised closed years; no broker access or 2026 prices."""
    CACHE.mkdir(parents=True, exist_ok=True)
    frames, manifest, excluded = [], [], []
    for year in protocol["years"]:
        if year < 2005 or year > 2025:
            raise ValueError("Outside authorized historical research dates")
        url = protocol["data_source"].format(year=year)
        path = CACHE / f"XAUUSD_M5_{year}.json.gz"
        if not path.exists():
            temporary = path.with_suffix(".part")
            subprocess.run(["curl", "--fail", "--silent", "--show-error", "--location",
                            "--retry", "2", "--max-time", "90", url, "-o", str(temporary)], check=True)
            # Validate gzip/JSON before promoting a download into the cache.
            with gzip.open(temporary, "rt") as handle:
                json.load(handle)
            temporary.rename(path)
        with gzip.open(path, "rt") as handle:
            raw = pd.DataFrame(json.load(handle))
        valid, invalid = validate(raw, year)
        frames.append(valid)
        excluded.append(invalid)
        item = {"year": year, "url": url, "bytes": path.stat().st_size, "sha256": digest(path),
                "rows": len(raw), "valid_rows": len(valid), "quarantined_rows": len(invalid),
                "first_utc": valid.timestamp_utc.min().isoformat(),
                "last_utc": valid.timestamp_utc.max().isoformat()}
        manifest.append(item)
        print(json.dumps(item), flush=True)
    bars = pd.concat(frames, ignore_index=True)
    if not bars.epoch_seconds.is_monotonic_increasing or bars.epoch_seconds.duplicated().any():
        raise ValueError("Combined history is unordered")
    bars.to_pickle(CACHE / "validated.pkl")
    pd.concat(excluded, ignore_index=True).to_csv(CACHE / "quarantined.csv", index=False)
    report = {"retrieved_utc": datetime.now(UTC).isoformat(), "attribution": protocol["attribution"],
              "bars": len(bars), "gap_intervals": int(bars.epoch_seconds.diff().gt(300).sum()),
              "files": manifest, "validated_sha256": digest(CACHE / "validated.pkl")}
    (CACHE / "MANIFEST.json").write_text(json.dumps(report, indent=2) + "\n")
    return bars, report


if __name__ == "__main__":
    retrieve(json.loads((ROOT / "goldnix_mtf/protocol.json").read_text()))
