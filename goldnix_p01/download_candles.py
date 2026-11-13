"""Resumable, rate-limited public M1 archive collection; never reads 2026 holdout."""

import argparse
import fcntl
from datetime import date, datetime, timedelta, UTC
import hashlib
import json
import lzma
from pathlib import Path
import time

import httpx
import numpy as np

CACHE = Path(__file__).resolve().parents[1] / "var/goldnix_p01_m1"
CANDLE_DTYPE = np.dtype(
    [("second", ">u4"), ("open", ">u4"), ("close", ">u4"), ("low", ">u4"), ("high", ">u4"), ("volume", ">f4")]
)


def decode(payload):
    raw = lzma.decompress(payload)
    if len(raw) % CANDLE_DTYPE.itemsize:
        raise ValueError("Truncated daily candle records")
    data = np.frombuffer(raw, CANDLE_DTYPE)
    if len(data) and (
        np.any(data["second"] >= 86400)
        or np.any(data["second"] % 60)
        or np.any(np.diff(data["second"].astype("int64")) <= 0)
    ):
        raise ValueError("Invalid daily minute timestamps")
    if len(data) and (
        np.any(data["high"] < np.maximum(data["open"], data["close"]))
        or np.any(data["low"] > np.minimum(data["open"], data["close"]))
        or not np.isfinite(data["volume"]).all()
        or np.any(data["volume"] < 0)
    ):
        raise ValueError("Invalid daily candle geometry or volume")
    return data


def collect(start, end, *, interval=1.5, limit=0):
    if not date(2003, 1, 1) <= start <= end < date(2026, 1, 1) or interval < 1:
        raise ValueError("Closed pre-2026 dates and at least one second per request required")
    CACHE.mkdir(parents=True, exist_ok=True)
    progress = {
        "start": str(start),
        "end": str(end),
        "requests_this_run": 0,
        "cached": 0,
        "downloaded": 0,
        "status": "running",
        "interval_seconds": interval,
    }
    next_request = 0.0
    with httpx.Client(
        timeout=45, follow_redirects=True, headers={"User-Agent": "GoldnixHistoricalResearch/1.0"}
    ) as client:
        current = start
        while current <= end:
            for side in ("BID", "ASK"):
                name = f"{current}_{side}"
                target = CACHE / f"{name}.bi5"
                receipt = CACHE / f"{name}.json"
                if target.exists() and receipt.exists():
                    item = json.loads(receipt.read_text())
                    if hashlib.sha256(target.read_bytes()).hexdigest() != item["sha256"]:
                        raise ValueError("Cached archive hash mismatch")
                    progress["cached"] += 1
                    continue
                if limit and progress["requests_this_run"] >= limit:
                    progress["status"] = "request_limit_reached"
                    break
                time.sleep(max(0.0, next_request - time.monotonic()))
                url = (
                    f"https://datafeed.dukascopy.com/datafeed/XAUUSD/{current.year}/"
                    f"{current.month - 1:02d}/{current.day:02d}/{side}_candles_min_1.bi5"
                )
                try:
                    response = client.get(url)
                    progress["requests_this_run"] += 1
                    next_request = time.monotonic() + interval
                    if response.status_code != 200:
                        progress.update(
                            status="stopped_http_error",
                            http_status=response.status_code,
                            retry_after=response.headers.get("retry-after"),
                            failed_url=url,
                        )
                        break  # No automatic retry, missing-data inference or access-control bypass.
                    data = decode(response.content)
                    temporary = target.with_suffix(".part")
                    temporary.write_bytes(response.content)
                    temporary.replace(target)
                    item = {
                        "date": str(current),
                        "side": side,
                        "url": url,
                        "downloaded_utc": datetime.now(UTC).isoformat(),
                        "bytes": len(response.content),
                        "sha256": hashlib.sha256(response.content).hexdigest(),
                        "records": len(data),
                        "zero_volume_minutes": int(np.sum(data["volume"] == 0)),
                        "kind": "provider M1 candles; not actual intraminute quotes",
                        "price_divisor": 1000,
                        "scale_basis": "Paired Bid/Ask 2005-06-01 probe independently agrees with cached M5 within0.005",
                    }
                    receipt.write_text(json.dumps(item, indent=2) + "\n")
                    progress["downloaded"] += 1
                    progress["last_file"] = name
                except (httpx.HTTPError, ValueError, lzma.LZMAError) as exc:
                    progress.update(
                        status="stopped_transport_or_validation_error", error=str(exc), failed_url=url
                    )
                    break
                progress["updated_utc"] = datetime.now(UTC).isoformat()
                (CACHE / "PROGRESS.json").write_text(json.dumps(progress, indent=2) + "\n")
                if progress["downloaded"] % 20 == 0:
                    print(json.dumps(progress), flush=True)
            if progress["status"] != "running":
                break
            current += timedelta(days=1)
        if current > end:
            progress["status"] = "complete"
    progress["updated_utc"] = datetime.now(UTC).isoformat()
    (CACHE / "PROGRESS.json").write_text(json.dumps(progress, indent=2) + "\n")
    print(json.dumps(progress), flush=True)
    return progress


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", type=date.fromisoformat, default=date(2005, 5, 30))
    parser.add_argument("--end", type=date.fromisoformat, default=date(2025, 12, 31))
    parser.add_argument("--interval", type=float, default=1.5)
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()
    CACHE.mkdir(parents=True, exist_ok=True)
    with (CACHE / "collector.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        collect(args.start, args.end, interval=args.interval, limit=args.limit)
