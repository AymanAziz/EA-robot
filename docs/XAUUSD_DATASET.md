# XAUUSD H1 historical dataset

## Delivered result

The selected zero-cost source is **EV Trading Labs**. The local, consolidated
CSV contains 136,732 XAUUSD H1 bars from 23 closed-year files:

- file: `var/xauusd_history/xauusd_h1_20030505_20251231_bid_ask.csv`
- coverage: `2003-05-05T00:00:00Z` through `2025-12-31T21:00:00Z`
- size: 13,761,303 bytes; 136,733 lines including the header
- SHA-256: `c680f6cd394384ee1a21f7a82cb859f1eff00949ac945208a9c457829788f989`
- metadata and per-year hashes:
  `var/xauusd_history/xauusd_h1_20030505_20251231_bid_ask.metadata.json`

This is more than 22 years of hourly data. The publisher's live catalogue
lists XAUUSD at M1, M5, M15, H1, H4 and D1 for 2003–2026. This export stops at
the last closed year, 2025, so it does not mix a partial 2026 file into a
historical test. The first catalogue year is partial, which the publisher says
can happen for an instrument's first year.
[EV Trading Labs data catalogue](https://evtradelabs.com/data)

## Source, licence and attribution

EV Trading Labs says its files are free to use **with attribution**, and says
closed-year H1 files require no account. Keep this attribution with any result
derived from the data:

> Data source: EV Trading Labs (https://evtradelabs.com/data).

The catalogue also labels the data educational, gives no accuracy guarantee,
and says use is at the user's risk. Its general terms protect the publisher's
content and materials. The one-line data licence is not a standard open-data
licence and does not spell out a right to republish the raw files, so this
project keeps the raw downloads and consolidated CSV under the git-ignored
`var/` directory. Ask the publisher before redistributing the raw dataset.
[dataset licence and disclaimer](https://evtradelabs.com/data),
[EV Trading Labs terms](https://evtradelabs.com/terms)

EV Trading Labs states that the series was aggregated from Dukascopy ticks and
that H1 is a pre-computed resample of M1. That is the **publisher's provenance
claim**; this project did not receive the original tick archive or independently
prove the upstream lineage. EV's XAUUSD statistics page repeats the claimed
Dukascopy-tick origin and UTC aggregation.
[EV XAUUSD methodology](https://evtradelabs.com/stats/XAUUSD)

## Data contract

EV publishes one gzip-compressed JSON array per symbol, timeframe and calendar
year. It documents the raw columns as `ts, o, h, l, c, ao, ah, al, ac, v`, with
`ts` in Unix epoch seconds UTC, no daylight-saving conversion, and each bar
stamped at its opening time. It also documents H1 as a pre-computed M1
resample.
[EV file and timestamp specification](https://evtradelabs.com/data)

The consolidated CSV is:

```text
timestamp_utc,epoch_seconds,bid_open,bid_high,bid_low,bid_close,ask_open,ask_high,ask_low,ask_close,provider_volume
```

| CSV field | EV raw field | Meaning |
| --- | --- | --- |
| `timestamp_utc` | derived from `ts` | ISO-8601 UTC bar-open timestamp |
| `epoch_seconds` | `ts` | Unix seconds at bar open |
| `bid_open/high/low/close` | `o/h/l/c` | hourly bid-side OHLC |
| `ask_open/high/low/close` | `ao/ah/al/ac` | hourly ask-side OHLC |
| `provider_volume` | `v` | provider-reported volume; units are not documented |

EV describes the files as containing bid and ask. The `a*` fields are mapped to
the ask side; observed open and close ask prices are never below their matching
bid prices. There is no native midpoint column. If a midpoint is needed,
averaging bid and ask open/close is explicit, but averaging separately
aggregated bid/ask highs or lows is not an exact tick-derived midpoint high or
low.
[EV bid/ask description](https://evtradelabs.com/data)

Do not interpret `provider_volume` as centralized physical-gold or exchange
volume: EV does not document its unit or definition. XAUUSD here is a
broker-derived spot/CFD quote history, not a centralized exchange tape.

## Reproducible download and conversion

The first-party annual endpoint used by the catalogue is:

```text
https://evtradelabs.com/api/simulator/data/XAUUSD/H1/{year}.json.gz
```

The following downloads the same closed-year range sequentially. EV does not
publish a numeric request-rate limit, so the command deliberately avoids
parallel requests, pauses between years, and retries transient errors.

```bash
raw_dir='var/xauusd_history/evtradelabs_h1_json'
mkdir -p "$raw_dir"

for year in {2003..2025}; do
  curl --fail --location \
    --retry 5 --retry-all-errors --retry-delay 2 \
    --output "$raw_dir/$year.json.gz" \
    "https://evtradelabs.com/api/simulator/data/XAUUSD/H1/$year.json.gz"
  gzip -t "$raw_dir/$year.json.gz"
  sleep 1
done
```

This Python-standard-library conversion preserves both quote sides, uses UTC,
and does not fill or interpolate missing hours:

```bash
python3 - <<'PY'
import csv
import gzip
import json
from datetime import datetime, timezone
from pathlib import Path

raw_dir = Path("var/xauusd_history/evtradelabs_h1_json")
output = Path("var/xauusd_history/xauusd_h1_20030505_20251231_bid_ask.csv")
header = [
    "timestamp_utc", "epoch_seconds",
    "bid_open", "bid_high", "bid_low", "bid_close",
    "ask_open", "ask_high", "ask_low", "ask_close",
    "provider_volume",
]

with output.open("w", encoding="utf-8", newline="") as target:
    writer = csv.writer(target, lineterminator="\n")
    writer.writerow(header)
    for year in range(2003, 2026):
        with gzip.open(raw_dir / f"{year}.json.gz", "rt", encoding="utf-8") as source:
            rows = json.load(source)
        for row in rows:
            timestamp = datetime.fromtimestamp(
                int(row["ts"]), tz=timezone.utc
            ).strftime("%Y-%m-%dT%H:%M:%SZ")
            writer.writerow([
                timestamp, row["ts"],
                row["o"], row["h"], row["l"], row["c"],
                row["ao"], row["ah"], row["al"], row["ac"], row["v"],
            ])
PY

wc -l var/xauusd_history/xauusd_h1_20030505_20251231_bid_ask.csv
shasum -a 256 var/xauusd_history/xauusd_h1_20030505_20251231_bid_ask.csv
```

Expected output is 136,733 lines and the SHA-256 shown above. The publisher
does not provide a version identifier or checksum manifest, so the local raw
file hashes in the metadata are the reproducibility anchor for this retrieved
snapshot.

## Validation performed

The consolidated file passed these structural checks:

- timestamps are unique, strictly increasing and aligned to UTC hours;
- all prices are finite and positive;
- bid and ask OHLC invariants hold (`low <= open/close <= high`);
- open and close ask-minus-bid spreads are nonnegative;
- provider volume is nonnegative;
- no gap was filled, interpolated or converted into a synthetic flat bar.

There are 4,133 gaps larger than one hour, representing 61,914 absent clock
hours. Most are expected market closures, but this check cannot distinguish a
holiday/weekend from every possible upstream outage. Backtests must retain the
gaps, reject stale prices, and never assume an hourly bar exists continuously.

## Research limitations

- Bid/ask H1 bars support spread-aware research, but not exact tick-path,
  slippage, market-depth or fill simulation.
- Separately aggregated bid and ask OHLC do not reveal the exact intrabar
  spread at every instant.
- A Dukascopy-derived series can differ from the user's broker in price,
  spread, session breaks, rollover, financing and execution.
- Historical quotes and a clean structural validation do not demonstrate an
  executable trade, a greater-than-50% win rate, or future profit.
- Run chronological train/validation/test splits and model realistic spread,
  slippage, financing and latency before drawing a performance conclusion.
