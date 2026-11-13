# D01 experimental MT5 demo

The user explicitly requested demo activation after reviewing the failed H02/H03
results. `GoldnixMTFDemo` v2.00 implements the requested H4 → H1 → M15 → M5
sequence and retains the existing profit protection and shared daily limits.
It is an **experimental demo, not a Step 6 or Step 7 PASS**.

The saved chart is **XAUUSD.c M1**. H1 supplies entries: attaching this EA to M1
does not turn its H1 setup into an M1 setup. It supports both BUY and SELL,
only one position, 0.01 lot, and a maximum planned loss of 5 USC ($0.05).
If H1 volatility makes that minimum lot too risky, the EA skips the trade.

## What the EA does

1. Reconstruct separate Bid/Ask M5 OHLC from broker ticks; require all 12 M5
   candles for an H1 aggregate and all 48 for H4. Incomplete intervals are
   excluded. Forming candles never supply signals.
2. Require 100 complete H4 bars. BUY needs midpoint close above EMA50 and a
   rising EMA over three completed H4 bars; SELL uses the exact opposite.
3. Enter only on a fresh H1 midpoint close beyond the preceding 20-bar channel,
   in agreement with H4. Use simple ATR14, distance `max(2 × ATR, 0.5)`, original
   three-distance TP, and the existing spread, risk, margin and session checks.
4. Freeze the broken channel level and `max(signal spread, 0.1 × H1 ATR)` buffer.
   An entire M15 interval after confirmed entry must close back inside that
   level to warn. The next consecutive M5 must confirm; a reclaim or missing
   confirmation candle cancels the warning. A confirmed exit persists until
   an executable quote is available. Original SL/TP remain active throughout.
5. Independently retain P01 profit protection: arm at half original price risk,
   subject to the cost reserve, and tighten SL to retain half the observed
   favorable excursion. A floor breach creates a durable close request.
   This does not guarantee a profit or prevent a gap through the stop.

The broker's candle clock is intentional. Historical research used UTC, and
H03 did not include P01 profit protection. D01 is therefore a new variant;
the research certificate cannot be transferred. See [PROTOCOL.md](PROTOCOL.md).
The first post-entry M15 interval must begin after order confirmation, which
can defer the first warning compared with a bar-open research fill.

The EMA bootstrap uses 7,200 recent closed M5 bars, and includes at least 100
complete H4 observations before readiness. Reopening can slightly change the
EMA seed. Restart with an existing owned position follows the preserved P01
recovery-close policy; it does not reconstruct or forget an old profit peak.

## Qualification versus engineering

| Check | Result |
| --- | --- |
| H02 research Step 6 | FAIL: 647 trades versus 1,000 required |
| H03 research Step 6 | FAIL: 732 trades and negative return lower bound |
| D01 Step 6 | NOT QUALIFIED: new broker-clock/protection variant needs its own full validation |
| D01 Step 7 | NOT RUN: no untouched frozen holdout and no qualified Step 6 |
| Shared native policy | 4,822 assertions, zero failures; includes 4,799 chronological ingestion assertions |
| C++ policy versus independent pandas | 33,994 rows across four real-history/missing-bar fixtures |
| Native MQL policy versus independent pandas | 8,500 rows, all fields within 1e-8 |
| Existing H02/MTF/Step 6 regression tests | 39 passed; 15 existing NumPy deprecation warnings |

[Deployment evidence](evidence/DEPLOYMENT.json) records the final installed
binary/source hashes, broker-history feature comparison, saved M1 chart,
normal application reopening, and preservation of the actual risk checkpoint.
These are engineering checks. The new full EA order lifecycle has not acquired
a new historical profitability or trade-path parity certificate.

At handoff, the account was flat with three daily attempts and −2.009649 R.
The −2R entry halt is retained. No order was forced to demonstrate activity.
A normal forward Malaysia-day rollover resets the daily quota only when flat;
an eligible signal and an open broker session are still required afterwards.
The EA runs only while MT5 and its connection are running. Reopening MT5 loads
the saved EA automatically and warms its history before considering entries.

## Reproduce and inspect

```sh
clang++ -std=c++17 goldnix_mtf_demo/tests/policy.cpp -o /tmp/goldnix_mtf_policy
/tmp/goldnix_mtf_policy
PYTHONPATH=goldnix:. .venv/bin/python -m goldnix_mtf_demo.verify
.venv/bin/python -m goldnix_mtf_demo.ops compile
.venv/bin/python -m goldnix_mtf_demo.ops status
PYTHONPATH=goldnix:. .venv/bin/python -m goldnix_mtf_demo.finish
```

`ops activate` performs the authorized local demo handoff: it requires a fresh
flat verified demo, backs up current settings privately, disables trading for
the order-free native probe, then replaces exactly the recognized saved M1
expert. It never restores an old risk checkpoint. `finish` is read-only with
respect to MT5; it refuses to certify readiness, an unexpected fill, or a
changed risk state. Its no-order check is for the activation run and should
not be interpreted as a requirement that the future experiment never trades.

`build_source.py` preserves the P01 account identity, cent-account sizing,
position ownership, reconciliation, daily limits, SL/TP and profit manager.
It replaces the entry/context driver and adds a checksummed fakeout journal.
The generated [GoldnixMTFDemo.mq5](GoldnixMTFDemo.mq5) is committed for review;
compilation copies its four unchanged P01 headers from `goldnix_auto_m1`.
Old P01 sources and binary remain available for rollback. Credentials, login,
terminal profiles, quote archives and executable binaries stay out of Git.
