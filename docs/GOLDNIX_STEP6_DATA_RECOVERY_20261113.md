# Step 6 historical quote recovery — 2026-11-13

**Result: no qualified full-era replacement was established.** The original
2005-start eras remain unchanged. A real March 2009 HistData tick archive was
downloaded and decoded, but its prices contradict the publisher's documented
Bid/Ask order. It is quarantined as evidence, not admitted to strategy testing.
The bounded Dukascopy 2005 tick probe timed out again. These findings do not
complete Step 6 or authorize Step 7.

This continuation uses the Matt Pocock research workflow. All new probe files
are separate in `var/goldnix_step6_recovery/`. Existing data, strategy code, MT5,
accounts and orders were not changed. No 2026 price payload or Step 7 dataset
was opened. The catalogue page itself includes links to later years; those
links were not followed for price acquisition.

## Acquisition evidence

Public data requests were serial, separated by at least 15 seconds after the
previous completed request, with zero automatic retries and an immediate-stop
policy for HTTP 429. No 429 occurred. Request and response metadata are saved
beside each artifact. Only the following archive was acquired; no bulk download
was started.

| Request, UTC on 2026-11-13 | Outcome |
| --- | --- |
| HistData XAUUSD tick catalogue, completed 07:04:32 | HTTP 200; earliest listed year 2009. |
| Dukascopy 2005-06-01 10:00 tick hour, 07:05:11–07:05:46 | Connection timeout after 35 seconds; no response body or HTTP status. |
| HistData 2009 catalogue, 07:06:34–07:06:35 | HTTP 200; monthly links run from March through December. |
| HistData March 2009 download page, 07:06:57–07:06:58 | HTTP 200; public form provides the archive download. |
| HistData public archive form, 07:09:20–07:09:21 | HTTP 200; ZIP, 1,526,638 bytes. |

The catalogue and year page are direct observations of the first-party
[XAUUSD tick catalogue](https://www.histdata.com/download-free-forex-data/?/ascii/tick-data-quotes/xauusd)
and [2009 monthly catalogue](https://www.histdata.com/download-free-forex-historical-data/?/ascii/tick-data-quotes/xauusd/2009).
They do not certify completeness of every linked month.

The archive came from the ordinary form on the
[March 2009 page](https://www.histdata.com/download-free-forex-historical-data/?/ascii/tick-data-quotes/xauusd/2009/3),
POSTing its supplied fields to `https://www.histdata.com/get.php`. No account,
payment, FTP credentials or access-control bypass was involved. Public form
tokens are transient; reproduce from a fresh page, not a guessed download URL.

## Decoded HistData fixture and rejection reason

The [published specification](https://www.histdata.com/f-a-q/data-files-detailed-specification/)
defines Generic ASCII ticks as `DateTime,Bid,Ask,Volume`, with a millisecond
timestamp and fixed EST throughout the year. Conversion therefore adds five
hours to obtain UTC; using New York daylight-saving rules would be incorrect.
Its M1 bars contain Bid OHLC only. Its NinjaTrader tick format is described as
one-second bars, so it is not a substitute for the Generic ASCII event stream.

Local files:

- `histdata_xauusd_ticks_200903.zip`: original downloaded ZIP.
- `DAT_ASCII_XAUUSD_T_200903.csv`: original member bytes, unmodified.
- `DAT_ASCII_XAUUSD_T_200903.txt`: publisher's accompanying gap report.
- `histdata_xauusd_ticks_200903.audit.json`: decoded counts, sample quotes,
  timestamp conversion, daily counts and quarantine decision.
- `histdata_xauusd_ticks_200903.download.metadata.json`: HTTP provenance.

The complete CSV has 310,410 syntactically valid records. Its observed UTC span
is **2009-03-15 22:00:14 through 2009-04-01 04:58:34**, covering 16,670 distinct
UTC minutes. The month name refers to fixed-EST timestamps, so the UTC end
extends into April.

| Audit under the documented column order | Count |
| --- | ---: |
| Ask below Bid | 309,466 |
| Ask equal to Bid | 944 |
| Ask above Bid | 0 |
| Nonpositive prices / malformed rows / backward timestamps | 0 |
| Nonzero millisecond suffixes | 0 |
| Same timestamp as preceding record | 29,469 |
| Same timestamp but changed price pair | 29,452 |
| Nonzero volume | 0 |
| Inter-record gaps greater than 60 seconds | 680 |

For example, the raw row `20090315 180030000,925.850000,924.950000,0`
would mean Bid 925.85 and Ask 924.95 under the published schema. This is a
systematic contradiction, not an isolated outlier. Reversed fields are a
plausible hypothesis, but no first-party correction was obtained. **Do not
swap columns, drop offending records, invent spreads or admit the archive to
an executable-price test without resolving the schema conflict.**

Every timestamp ends in `000` despite the nominal millisecond field. There are
many different quotes sharing the same second; their original file order must
be retained. This sample does not establish subsecond timing precision needed
to prove a one-second management path. Zero volume supplies no observed volume
signal. The longest raw inter-record gap is 172,825 seconds; this includes
calendar closures, so it is not automatically a missing-data defect. The
publisher's status report uses a different gap convention and cannot replace
an explicit session-aware coverage audit.

## Dukascopy recovery and full-era implications

The new request targeted
[2005-06-01 10:00 UTC ticks](https://datafeed.dukascopy.com/datafeed/XAUUSD/2005/05/01/10h_ticks.bi5).
The URL's month is zero-based. `duka_20050601T10Z.metadata.json` records the
connection timeout. A timeout does not show that the historical object is
absent. No conclusion about earliest tick availability can be drawn from it.

The existing `var/goldnix_p01_m1/collector.log` records HTTP 503 at 06:20 and
again at 06:34 UTC, after a bounded continuation acquired two more files.
The preserved cache has 32 calendar days of paired M1 files (64 files) from
May 30 through June 30, 2005. The last failed URL was
[July 1 BID M1](https://datafeed.dukascopy.com/datafeed/XAUUSD/2005/06/01/BID_candles_min_1.bi5).
It was not requested again in this continuation.

Subsequent main-session update at 07:21 UTC: a bounded resume successfully
acquired July 1 BID and ASK, bringing the shared cache to 33 paired calendar
days and 66 files. A further serial resume stopped on HTTP 503 for July 2 BID
at 07:21:53 UTC; it is no longer running. The current audit records 27,039
observed minutes, 20,477 placeholders and four unexplained zero-volume minutes.
This acquisition does not change the tick-coverage qualification result above.

Previously decoded 2018 and 2024 Dukascopy tick hours, plus a 2005 paired M1
day, remain useful format fixtures; see
[the earlier continuation](GOLDNIX_P01_DATA_CONTINUATION_20261113.md). Paired
M1 candles do not establish the tick sequence between high and low, simultaneous
Bid/Ask movement or the timer-driven exit path. The
[official historical export](https://www.dukascopy.com/swiss/english/marketwatch/historical/)
is a source route, not evidence that all required years were acquired.

HistData's verified catalogue cannot supply the required 2005–2008 interval,
and its first downloaded month also has unresolved quote semantics. Its
[FTP page](https://www.histdata.com/download-by-ftp/)
advertises paid access to the same data as the website; paying for transfer
does not establish earlier history or repair the schema. No purchase was made.

The practical next data step is a controlled resume of the original Dukascopy
cache, preserving every transport failure and coverage gap, followed by tick
coverage over the union of baseline and candidate exposure windows. That route
remains unverified for the whole 2005–2025 span. Retain the frozen eras and
performance gates. Neither switching the start to 2009 nor treating M1 candles
as observed intraminute execution would resolve the existing qualification gap.

## SHA-256 provenance

All paths below are relative to `var/goldnix_step6_recovery/`.

| Artifact | SHA-256 |
| --- | --- |
| `histdata_xauusd_ticks.html` | `1597475fe567ffc268a8b688ca163762575acfe29b2f71e68fc422b036864cb6` |
| `histdata_xauusd_ticks_2009.html` | `46673ca6d12b3a24cfd005a4e196dafd87ac48a71254751115bdfb2890fceef4` |
| `histdata_xauusd_ticks_200903.html` | `a6a5b92cfe7974b2de2c08b85ff343d06e153646c71f9e6c31abeedc26e52c63` |
| `histdata_xauusd_ticks_200903.zip` | `a1cf52f83622969c4c5ff385d8ba2cfd0b02c5ebc3ed563529d985f7ce68eac9` |
| `DAT_ASCII_XAUUSD_T_200903.csv` | `866c8eaa6ee273d8558511e0b54913b406603cdd07dd20ead13118086a707d6b` |
| `DAT_ASCII_XAUUSD_T_200903.txt` | `aa81dba6727d0cb95794db1f34b6d21a2ce84d4003518b570333e99d0bd21119` |
