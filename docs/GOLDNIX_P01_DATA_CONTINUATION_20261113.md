# P01 data continuation — 2026-11-13

Research continuation of `GOLDNIX_M1_PROTECTION_STEPS_RESEARCH_20261113.md`, using the Matt Pocock research workflow. Scope: first-party data access, binary validation, and MT5 tester semantics for the existing M1 protection protocol. No MT5 launch/restart, account changes, orders, credentials, paid storage access, or 2026 price payloads were used.

## Result

Two historical tick hours and one complete BID/ASK M1 calendar day were downloaded and validated. This supplies usable decoder fixtures and a promising, much smaller M1 acquisition route. It does **not** establish four-era completeness or pass any strategy-performance gate.

Raw evidence and metadata are in `var/goldnix_p01_ticks/probes/`. Every price request was serial, with at least 15 seconds between completed requests, a 30-second timeout, zero retries, and an immediate-stop policy for HTTP 429. The four initial tick requests were followed by two explicitly requested M1 probes. No 429 occurred in this continuation; two tick requests timed out. Timeout is an unknown result, not evidence of absent history.

| Payload requested, UTC | Result | Compressed bytes | Decoded records |
| --- | --- | ---: | ---: |
| 2024-02-01 10:00 tick hour | HTTP 200 | 25,357 | 5,859 |
| 2018-06-01 10:00 tick hour | HTTP 200 | 19,790 | 4,649 |
| 2013-06-03 10:00 tick hour | Timeout | — | — |
| 2005-06-01 10:00 tick hour | Timeout | — | — |
| 2005-06-01 BID M1 day | HTTP 200 | 13,189 | 1,440 |
| 2005-06-01 ASK M1 day | HTTP 200 | 12,841 | 1,440 |

The earliest XAUUSD **tick** date remains unverified from first-party evidence obtained here. The known earlier 2012 HEAD response proves an object responded, not its decoded contents or an instrument inception date. The successful 2005 candle day establishes M1 availability on that date only. Do not turn third-party “2003” availability claims into a verified coverage boundary.

## Free routes and bulk access

Dukascopy advertises its [Historical Data Export](https://www.dukascopy.com/swiss/english/marketwatch/historical/) as free CSV export from tick to monthly periods. Its current embedded interface is [the official export widget](https://widgets.dukascopy.com/en/historical-data-export). The same official page directs demo/live JForex users to Tools → Historical Data Manager. This research did not create an account or log in.

For an existing authorized JForex session, [`IHistory`](https://www.dukascopy.com/client/javadoc3/com/dukascopy/api/IHistory.html) supplies `getTicks` and background `readTicks`; `getTicks` loads the requested interval into memory, so bounded intervals are appropriate. This is an official API route, not proof that an unauthenticated SDK session can download the complete archive.

The official [bulk archive guide](https://wiki.dukascopy.com/en/development/data-export) describes AWS S3 Requester Pays and requires AWS credentials. It is not a free anonymous bulk alternative and was not accessed. Its daily tick layout is LZMA, 20-byte big-endian records, zero-based path months, and milliseconds from UTC day start. The guide warns that legacy hourly files have a different time base and commodities require verified price scaling. Its commented `XAUUSD: 100` example is **not valid evidence for the hourly samples below**.

No documented free single-request full-history bulk export was established. Public daily M1 files plus selectively acquired exposure ticks are a concrete route worth implementing; aggregate downloads still require coverage accounting and respectful rate control.

The current widget's [main script](https://widgets.dukascopy.com/en/main-QHB2P437.js) routes historical export to [this public component script](https://widgets.dukascopy.com/en/chunk-yOr7BamP.js). Inspection of its date normalization shows **MINUTE exports clamped to one calendar day**, from midnight to 23:59:59.999 on the selected start date. This is evidence against assuming its UI provides monthly/yearly M1 exports. No documented larger-range M1 endpoint was found, and no internal endpoint range was guessed or tested. Script URLs, hashes and relevant source contexts are retained in `widget_*inspection.json`; these are observations of the current implementation, not a stable API contract.

## Validated hourly tick decoder

Observed source URLs:

- [2018 tick hour](https://datafeed.dukascopy.com/datafeed/XAUUSD/2018/05/01/10h_ticks.bi5)
- [2024 tick hour](https://datafeed.dukascopy.com/datafeed/XAUUSD/2024/01/01/10h_ticks.bi5)

Both payloads decode with Python `lzma.decompress` and `struct.iter_unpack('>IIIff', raw)`. The fields are hour-relative milliseconds, integer ask, integer bid, ask volume, bid volume. Compute `timestamp_ms = UTC_hour_epoch_ms + offset`; divide each price integer by **1,000**. This is empirically validated for these two hourly files, not assumed from the daily-archive example.

Both samples have monotonic offsets inside `[0, 3_600_000)`, positive prices with ask ≥ bid, and finite nonnegative volume. First/last offsets: 2018 **159 / 3,599,962 ms**; 2024 **60 / 3,599,960 ms**. Do not discard records merely because adjacent timestamps coincide; source ordering can matter.

Each hour was aggregated into 12 UTC M5 bars and compared with the existing same-year `var/goldnix_mtf_m5/` cache. Across both bid and ask OHLC, maximum absolute differences were **$0.004 for 2018** and **$0.005 for 2024**, consistent with the cache's two-decimal rounding. Alternative divisors 100, 10,000 and 100,000 fail grossly. These checks support timestamp alignment, field order and scale; they do not verify every historical hour or independent broker execution parity.

## Daily M1 route: validated 2005 sample

Both first-party files succeeded:

- [2005-06-01 BID candles](https://datafeed.dukascopy.com/datafeed/XAUUSD/2005/05/01/BID_candles_min_1.bi5)
- [2005-06-01 ASK candles](https://datafeed.dukascopy.com/datafeed/XAUUSD/2005/05/01/ASK_candles_min_1.bi5)

Observed decoding: LZMA → **24-byte** big-endian `>IIIIIf`. Field order is `seconds_since_UTC_day_start, open_integer, close_integer, low_integer, high_integer, volume_float`. Timestamp = UTC day start + seconds; empirical divisor **1,000**. This interpretation was checked against all matching cached M5 bars, rather than borrowed from the hourly schema.

Each side has exactly 1,440 minute-grid rows, valid OHLC and finite nonnegative volume. **317 rows have zero volume and flat carried-forward prices.** Naively aggregating all rows produces M5 deviations up to $0.567 BID / $0.649 ASK. Excluding zero-volume rows for this cache comparison gives **284 matching M5 bars on each side**, no missing or extra nonempty M5 intervals, and maximum OHLC difference **$0.005**.

Keep raw rows and an explicit no-quote flag. Do not present these flat rows as observed trade/tick activity, and do not silently fill the four wholly empty M5 intervals. The sparse-bar policy must be consistent with the target EA's broker-history convention. The volume field is not an MT5 integer tick count and must not be substituted for one without validation.

For this sample, the zero-volume masks are identical for BID and ASK; all 317 rows are flat and equal the preceding close. Use the joint conditions `volume == 0`, flat OHLC, and carry-forward agreement to classify a placeholder. A zero-volume row with moving OHLC, a disagreement between sides, or an unexplained gap requires separate investigation; do not silently delete it based on this one-day result. Aggregate the first open, maximum high, minimum low and final close of non-placeholder rows inside each UTC five-minute interval. Omit an interval only when every constituent minute is a validated placeholder. Retain volume and its source definition separately from tick count.

Implementation consequence: download and audit daily M1 BID/ASK history first, compute all entry candidates and required indicator warmup, then acquire tick hours covering the union of baseline and protected-strategy exposure windows. Include entry fills, subsequent position-dependent entry eligibility, cooldowns, trailing updates, rollover and the final closing tick. Restricting acquisition to already profitable trades would bias the evaluation. M1 OHLC alone cannot resolve stop-versus-target order or one-second profit giveback.

## MT5 implications for the native adapter

[`CopyTicksRange`](https://www.mql5.com/en/docs/series/copyticksrange) takes inclusive millisecond endpoints and returns oldest-first ticks. Check both returned count and `GetLastError`: a timeout can return partial data. Adjacent chunks must avoid duplicate endpoints without dropping distinct ticks that share a millisecond. Tick flags identify changed fields; other fields can retain their previous values.

The [tester runtime documentation](https://www.mql5.com/en/docs/runtime/testing) says its tick cache is limited to **128,000 ticks**. `CopyTicks` can retrieve outside that cache only in real-tick mode. Real-tick testing can replace missing or inconsistent minutes with generated ticks; its underlying tick database is not corrected in the same way. Consequently, a database export need not equal the event stream processed by the EA. Capture generated events incrementally rather than assume an end-of-test historical query recovers the whole run. The same documentation says timer-based indicator reads use the latest tick's calculated state.

The [official tester-time chapter](https://www.mql5.com/en/book/automation/tester/tester_time) confirms that timer handlers run in every test mode, including seconds between bar-open ticks. `TimeLocal`, `TimeTradeServer` and `TimeGMT` coincide in the tester; broker-to-UTC offset therefore needs an explicit tested convention. Timer callbacks do not create new quote observations. [`OnTimer`](https://www.mql5.com/en/docs/event_handlers/ontimer) also documents event coalescing when a previous timer event is queued or processing.

One documentation tension needs native measurement: the [`TimeTradeServer` reference](https://www.mql5.com/en/docs/dateandtime/timetradeserver) says it equals `TimeCurrent` in testing, while the runtime's Sleep/synchronization example distinguishes current simulated server time from last-tick time. [`TimeCurrent`](https://www.mql5.com/en/docs/dateandtime/timecurrent) is defined in other handlers as last-quote time. Record all clocks, callback sequence and last quote timestamp on idle intervals before certifying a one-second adapter. A timer test that merely counts callbacks is insufficient.

## Evidence retained and remaining work

`probe_run_20261113.json` indexes the four tick probes. Individual `*.metadata.json` files include request times, source URLs, HTTP outcome, raw SHA-256, decoder checks and cache comparisons. The two candle metadata files additionally retain both naive and nonzero-volume aggregation results.

1. Integrate the four successful raw files as data-decoder fixtures. Keep daily candles and hourly ticks as separate formats and retain source hashes.
2. Establish full daily M1 coverage for each frozen era, explicitly classifying no-quote intervals, missing responses and transport failures. The 2005 day is a successful specimen, not a coverage certificate.
3. Obtain the required tick exposure windows and preserve a complete missing-window manifest. Resume only within provider limits; stop and respect any `Retry-After` response. No further downloads were started here.
4. Compare the native captured event stream and independent replay using the same time convention and frozen strategy. Generated-path engineering checks must remain distinguishable from real-tick performance evidence.
5. Keep the existing consumed 2026 holdout status and formal step criteria intact. These data-access successes do not change the pass/fail verdict.
