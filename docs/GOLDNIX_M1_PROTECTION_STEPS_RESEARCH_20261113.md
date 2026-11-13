# Qualifying M1 profit protection through Steps 1–8

Research date: 2026-11-13. This note maps the requested evaluation and checks
data access. It does not run a strategy backtest, access new holdout prices,
change MT5, or place orders.

## This is a new strategy revision

The original [build contract](../goldnix/BUILD_PROMPT.md) specifies **H1 Aroon**,
fixed exits and no trailing. The user has since authorized **M1 channel20 with
profit protection**, described in [P01's protocol](../goldnix_auto_m1/protection_protocol.json).
The eight-stage evaluation can be reused, but the new rules need their own
frozen strategy contract and results. Do not label the original strategy's
exact requirements as implemented by P01.

Record all production behavior before performance evaluation: completed M1
signals, midpoint construction, ATR, next executable entry, risk sizing,
spread/quote limits, timer cadence, stop rounding and freeze restrictions,
profit peak persistence, cost reserve, early exits, recovery, Malaysia-day
limits, sessions and broker time conversion. The reviewed execution-check
entry is not a channel signal and must remain outside strategy performance.

The historical registry already contains 82 registered variants through H01.
P01 requires a disclosed new registration; changing protection thresholds after
seeing its results creates another hypothesis, not a repair of the same frozen
candidate. [H01 registration](../goldnix_mtf2/replay_protocol.json).

## What each step requires now

| Step | P01 evidence required | What can honestly be done in this session |
|---|---|---|
| 1: signals | Closed-M1 channel20 and symmetric BUY/SELL tests; equality, warmup, stale/duplicate signals and no future information. | Execute native policy tests and independent Python signal comparisons; old Aroon tests are regression evidence only. |
| 2: data/parity | Valid UTC M1 Bid/Ask history, coverage/spread/gap audit, broker clock evidence and M1 ATR parity. | Audit captured quotes and available native history; this does not establish all four historical eras. |
| 3: simulator | Same entry/risk rules and causal one-second profit management, broker SL/TP precedence, fees, gaps, rejected modifications and durable state. | Behavioral and broker-model tests can pass. An independent complete P01 replay still needs implementation/verification. |
| 4: four eras/random baseline | Exact P01 simulation for eras A–D, plus 200 eligible random schedules per era matched by BUY/SELL count and the same management/risk rules. | Requires qualified historical inputs. Existing M5/H1 results cannot substitute. |
| 5: sensitivity | Predeclared spread/cost, latency and ambiguous-path diagnostics; report without replacing P01. | Test code and fixtures now; historical metric deltas require the same qualified inputs. |
| 6: G1–G9/freeze | All unchanged gates computed for P01, monthly bootstrap and one-year drawdown simulation; hash inputs/code/config. | Run only on an actual P01 trade population. Missing metrics are NOT_EVALUATED, never PASS. |
| 7: holdout | Once-only evaluation of a genuinely untouched, predeclared period after a matching freeze. | No qualifying untouched P01 holdout has been established. The old 2026 holdout is consumed. |
| 8: full EA parity | At least 95% matching entries/exits, direction and exit reason against an independent P01 simulator on identical broker history; formal approval requires 6 and 7. | Native protection fixtures validate execution engineering. They do not constitute full-strategy parity or formal Step 8 approval. |

The original gates remain in [rules.yaml](../goldnix/gates/rules.yaml): G1 mean
lower bound >0; G2 edge ≥0.10R; G3 edge lower bound >0; G4 ≥3 positive eras; G5
≥1,000 trades; G6 material-gap share ≤10%; G7 one-year p99 drawdown ≤12% of the
declared account; G8 fill-policy win-rate delta ≤8 percentage points in every
era; G9 ATR parity. The original Step 6 implementation uses 10,000 monthly
bootstrap resamples and 100,000 Monte Carlo paths. Reuse numerical gates, not
old metrics or an engine that lacks the new exits.

## Available inputs and gaps

- `var/goldnix_mtf_m5/MANIFEST.json` records **1,511,699 M5 bars** from 2005–2025.
  Five-minute OHLC cannot reconstruct the five constituent M1 signals or the
  order of one-second profit peaks and reversals. Interpolating those prices
  would introduce an invented execution path.
- `goldnix_step8_h01/out/S8_20261112T154654Z/ticks.bin` contains **generated**
  broker-history ticks for a previously examined February 2024 window. It is
  useful for engineering replay, not untouched validation or complete eras.
- Current M1 run archives and the single execution-check audit are recent,
  observed session evidence. They are insufficient for the original four-era
  study and its 1,000-trade gate.

MT5 generates ticks from minute bars when actual ticks are unavailable, even
within a real-tick-mode test. Generated ticks also use a minute's fixed spread,
whereas recorded spreads can change within that minute. P01's stop depends on
the observed intraminute peak, so this distinction changes possible outcomes.
Record actual real/generated coverage and gaps from the tester rather than
inferring it from the selected model. [MetaQuotes tick generation](https://www.metatrader5.com/en/terminal/help/algotrading/tick_generation).

### Source options checked

| Source | Useful capability | Verified limitation / next action |
|---|---|---|
| EV Trading Labs | Publisher lists XAUUSD M1 through 2003–2026, separate Bid/Ask OHLC and UTC bar-open timestamps. | **All M1 files require a free account**, including closed years. Unauthenticated HEAD probes for 2005 and 2025 returned HTTP403 in this session. Use authorized exports; do not bypass access controls. M1 OHLC still does not reveal the actual one-second path. [Catalogue](https://evtradelabs.com/data). |
| Dukascopy historical export / JForex history | Official export provides Bid/Ask; JForex exposes historical bars and ticks. | Establish XAUUSD date coverage, timestamp basis and price scale before bulk import. This is another venue's quote feed, not verified historical JustMarkets execution. [Export](https://www.dukascopy.com/api/data/get/historical-data-export), [history ticks](https://wiki.dukascopy.com/en/development/strategy-api/historical-data/history-ticks/). |
| Dukascopy documented S3 archive | Daily LZMA-compressed `.bi5` files; documented binary decoding. | Requires AWS credentials and **Requester Pays** billing. No billing action or credential access was performed. Commodity price scales must be verified; the documentation warns against blindly applying the FX default. [Official archive guide](https://wiki.dukascopy.com/en/development/data-export). |
| Current MT5 broker | Native `CopyTicksRange` and tester download can supply broker history where available. | Inventory first/last dates and real-tick coverage by era before running results. The earlier February 15, 2024 probe returned no real ticks for that sample; it does not prove every historical date is unavailable. [CopyTicksRange](https://www.mql5.com/en/docs/series/copyticksrange), [tester downloads](https://www.metatrader5.com/en/terminal/help/algotrading/test_preparation). |

Additional **HEAD-only** observations on the first-party public hourly feed:
`https://datafeed.dukascopy.com/datafeed/XAUUSD/2012/05/01/10h_ticks.bi5`
returned 200 / 24,378 bytes, and
`https://datafeed.dukascopy.com/datafeed/XAUUSD/2024/01/01/10h_ticks.bi5`
returned 200 / 25,357 bytes. A 2005 probe had a connection reset; subsequent
small probes returned **429**, so requests were stopped. These are access
observations, not decoded-data, coverage or accuracy certificates. No price
payload was downloaded. Retry only with compliant pacing/backoff; never turn
transport failures or rate limits into fabricated empty trading periods.

The documented daily S3 format and the observed hourly HTTP paths are distinct:
do not reuse a day-relative timestamp decoder on hour-relative files without
verifying its format. Hash originals, validate scale against independently
known prices, compare M1 aggregation, and preserve missing intervals explicitly.

## Holdout and approval boundaries

[Step 7 RESULT.json](../goldnix_step7/out/RESULT.json) records completed access on
2026-11-12 to **January–September 2026** for V1/V2. Its old README still says no
real holdout ran; the completed result and access receipt are authoritative.
Other October/November prices were used for parity and observed demo work.
The annual file was received, so its untested remainder must not automatically
be claimed sealed. A different timeframe over already examined calendar prices
does not create independent market history.

Preserve all existing access receipts. Establish a new period only after
auditing prior access; the clean fallback is a prospective period starting
after final P01 code/config are frozen. Merely waiting an hour does not establish
a meaningful trade population. Apply the existing collapse criterion once;
zero or one closed trade is insufficient under the current runner. Do not tune
on the result and then call the same period holdout again.

H01's earlier result is explicitly `engineering_status=PASS` but
`step8_status=NOT_PASSED`, with Step 7 absent. Its H1 signals/M5 execution do
not qualify M1 P01. Likewise, V1/V2's old holdout passes do not override their
Step 6 failures or qualify a new trailing strategy.
[H01 result](../goldnix_step8_h01/out/S8_20261112T154654Z/RESULT.json),
[post-holdout audit](../goldnix_checks/STEP6_AFTER_HOLDOUT.md).

## Reproducible next checks

Run the P01-native receipts and current signal comparison through their own
commands, preserving every output:

```sh
PYTHONPATH=goldnix:. .venv/bin/python -m goldnix_auto_m1.protection_validation policy-result
PYTHONPATH=goldnix:. .venv/bin/python -m goldnix_auto_m1.protection_validation tester-result
PYTHONPATH=goldnix:. .venv/bin/python -m goldnix_auto_m1.ops verify-signals
```

These read existing results/current records; they do not turn fixture trades
into strategy returns. The old `goldnix_step6.runner`, `goldnix_step7.runner`
and H01 parity runner are bound to their original frozen strategies. Do not
invoke them with P01 and reuse their labels. Build the new replay contract,
qualify inputs and freeze a new registration before historical performance
evaluation. Honest same-session outcomes may include successful software
checks alongside `NOT_EVALUATED`/`INSUFFICIENT_DATA` qualification steps.
