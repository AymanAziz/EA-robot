# XAUUSD M5 bid/ask data access for the separate Step 6 candidate

Checked **2026-11-12**. This is a data-access investigation, not a strategy
evaluation. No 2026 price file, MT5 state, running job, or frozen strategy was
accessed or changed for this subtask.

## Result: EV Trading Labs provides the required historical M5 files

Use the same publisher as the existing H1 research. Its catalogue states that
closed-year M5/M15/H1/H4/D1 files download without an account; M1 and the current
year require one. It lists XAUUSD from 2003, describes bid/ask candles aggregated
from Dukascopy ticks, and specifies UTC opening timestamps. The licence is
free use with attribution to EV Trading Labs.
[Publisher catalogue and download specification](https://evtradelabs.com/data).

The catalogue's public Dataset JSON-LD directly lists this download pattern:

```text
https://evtradelabs.com/api/simulator/data/XAUUSD/M5/{year}.json.gz
```

For **2005–2025**, it lists all 21 annual files, totalling **40,881,077 bytes
(38.99 MiB) compressed**. This is the advertised retrieval footprint, not a
claim that every trading interval is present. The complete set has not been
downloaded by this investigation. One-year-at-a-time retrieval is sufficient;
no tick archive or M1 account is required for the proposed M5 research.
[Published file catalogue](https://evtradelabs.com/data).

Keep raw quotes private and attach this attribution to derived reports:

> Data source: EV Trading Labs (https://evtradelabs.com/data).

The short data licence does not specify a broad redistribution right; the
general terms protect the publisher's materials. Do not treat this as a
standard open-data licence or publish the raw files.
[EV terms](https://evtradelabs.com/terms).

## Access probes and format actually observed

Ordinary native `curl`, without cookies, credentials, origin spoofing or special
headers, succeeded. Python's default `urllib` requests returned HTTP 403, so
that client response alone did not establish an account requirement. Web-tool
fetches also timed out. No challenge was solved or bypassed.

The following native `curl -I` HEAD probes all returned **HTTP/2 200** and
`Content-Type: application/gzip`:

| M5 year | Content-Length, bytes |
|---|---:|
| 2005 | 1,685,648 |
| 2010 | 2,034,878 |
| 2015 | 1,884,094 |
| 2020 | 2,063,513 |
| 2025 | 2,133,539 |

A single bounded GET of [the 2005 annual file](https://evtradelabs.com/api/simulator/data/XAUUSD/M5/2005.json.gz)
was decompressed and inspected in memory; no annual raw files were saved by
this subtask. Observations:

- 1,685,648 compressed bytes; 8,679,273 uncompressed JSON bytes.
- JSON array containing **71,693 rows**.
- First opening time: `2005-01-02T22:00:00Z`.
- Last opening time: `2005-12-30T21:55:00Z`.
- Fields: `ts,o,h,l,c,ao,ah,al,ac,v`; bid OHLC and ask OHLC are separate.
- All timestamps were divisible by 300; none were duplicate or decreasing.
- No negative open or close spreads were observed in this sample.
- SHA-256 of the compressed response:
  `7b71ff7873e2e3e87e55a01b464e434755cb19bd7021aa058f4c4fdacfac5462`.

The first observed row was:

```json
{"ts":1104703200,"o":437.43,"h":437.82,"l":437.2,"c":437.42,"ao":437.84,"ah":438.23,"al":437.65,"ac":437.82,"v":0.02005}
```

These checks establish access and basic shape, not complete data quality,
continuous coverage, intrabar chronology, or an executable JustMarkets price.
The fractional `v` values must not be silently renamed MT5 tick counts or
centralized gold trade volume.

## Causal aggregation and remaining data checks

The existing H1 files cannot reconstruct M5 candles. Download genuine M5
observations, then derive M15 and H1 from the **same M5 stream**, independently
for bid and ask: first open, maximum high, minimum low, final close. Freeze UTC
interval boundaries and publish a higher-timeframe candle only after its
interval ends. At an M5 decision time, never use the still-forming H1 or M15
candle. This is a proposed local data contract; it does not assume identical
chart construction across platforms.

Dukascopy's official history API distinguishes current incomplete bars from
completed bars, and its current chart manual describes instrument-specific
session boundaries. Session and UTC grids must therefore be explicit instead
of assuming every vendor chart is interchangeable.
[History-bar semantics](https://wiki.dukascopy.com/en/development/strategy-api/historical-data/history-bars),
[chart candle formation](https://wiki.dukascopy.com/en/manuals/jforex4-desktop/trading-sessions-logic).

Before simulation, record each raw file's source URL, retrieval time, byte count
and SHA-256; validate finite positive prices, per-side OHLC consistency,
timestamps, spreads, duplicates, year boundaries and gaps. Preserve missing
intervals and distinguish scheduled closures from unexplained missing data;
do not interpolate fabricated prices. Define how partial aggregate groups and
indicator warm-up gaps are handled before inspecting strategy results.

Bid/ask OHLC permits side-aware cost modelling but does not reveal the order of
intrabar extremes or every spread change. A bar touching both stop and target
needs a declared conservative/ambiguous treatment or finer evidence; separate
highs cannot establish simultaneous spread. Commission, slippage, contract
size, funding and broker-specific differences remain separate assumptions.
The existing consumed 2026 holdout stays outside this retrieval and evaluation.

## Dukascopy routes investigated as alternatives

The official visible Historical Data Export supports free CSV downloads from
tick to monthly resolution; JForex's Historical Data Manager is another export
route after platform login.
[Official export page](https://www.dukascopy.ch/swiss/english/marketwatch/historical/).

However, the website terms restrict downloads to personal non-commercial use,
prohibit database construction, and require prior written consent for automated
website acquisition. The free widget and legacy HTTP `.bi5` paths therefore do
not establish permission for an unattended bulk collector. No widget-price or
legacy-datafeed requests were made in this investigation.
[Dukascopy website terms](https://www.dukascopy.com/swiss/english/legal-pages/terms-of-use/).

The **documented programmatic archive** is
`s3://cfg-public-proper-wallaby`, region `eu-west-1`, with **AWS Requester Pays**.
It requires valid AWS credentials and charges requests/transfers, so it is not
the free credentialless fallback. The guide documents daily LZMA `.bi5` files
at `SYMBOL/YEAR/MONTH/DAY_ticks.bi5`, zero-based months, and 20-byte big-endian
records containing millisecond offsets, ask/bid integers and ask/bid volumes.
Confirm instrument-specific price scaling; do not guess XAUUSD's divisor from
currency pairs or conflate this daily layout with older hourly HTTP files.
[Official archive guide](https://wiki.dukascopy.com/en/development/data-export).

No AWS credentials or paid requests were used, and no full Dukascopy coverage
listing was retrieved. The earlier local [source investigation](GOLD_FREE_DATA_RESEARCH.md)
recorded provider metadata giving XAUUSD minute/tick history from 2003-05-05;
that is historical metadata, not a fresh all-years completeness check.
The now-verified EV M5 route is the practical choice for the authorized
2005–2025 research window.
