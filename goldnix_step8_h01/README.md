# H01 Step 8 — execution parity passes; qualification pending

**The MT5/Python trade comparison passes: 5/5 matching trades (100%), against
the unchanged 95% requirement. Full Step 8 sign-off remains blocked because
H01 has no qualifying Step 7 result.**

This is a small engineering sample using MT5-generated ticks from broker M1
history, not actual historical ticks or evidence of profitable trading.

The completed run is [`S8_20261112T154654Z/RESULT.json`](out/S8_20261112T154654Z/RESULT.json).
See the [native MT5 report](out/S8_20261112T154654Z/tester_report.htm),
[all trade comparisons](out/S8_20261112T154654Z/trade_comparison.csv),
[journal reconciliation](out/S8_20261112T154654Z/VERIFICATION.json), and
[account restoration receipt](out/S8_20261112T154654Z/RESTORED.json).

| Check | Result |
|---|---|
| Entry/exit bar, direction and exit reason | 5/5 match; 3 BUY, 2 SELL |
| Extra, missing or mismatched trades | 0 |
| Signal, ATR, stop-distance and spread calculations | 564/564 match |
| Processed quotes exported | 2,841,501 generated bid/ask ticks |
| Reconstructed history | 664 H1 bars; 7,955 M5 bars |
| Processed Bid OHLC versus separate broker H1 export | All 664 bars exactly match |
| Independent journal reconciliation | All 10 entry/exit deals match the EA export |
| Native compilation | 0 errors, 0 warnings |
| Harness regression tests | 12 pass |
| Rejected orders / unresolved positions | 0 / 0 |
| Original H01 strategy and risk settings | Unchanged; planned-risk cap remains $0.05 |
| Online demo after restoration | 1,979.82 USC; flat; trading disabled; no new deals |

The trading window is February 1 through February 29, 2024 at 22:00 UTC,
with warmup beginning January 22. This month was selected for known execution
activity in the frozen H01 record, including both directions; no P&L screen
or strategy parameter search was used. The previous recent window produced
zero trades. The frozen H01 record contains no trades in 2025, so simply
repeating the recent window would not establish order-path parity.

A read-only native probe retrieved 665 H1 bars for the earlier interval and
zero real ticks for the sampled day, February 15. This does not prove that
every earlier date lacks real ticks. The continuation explicitly uses tester
Model 0: generated Bid prices from actual broker M1 candles, with Ask derived
from each M1 bar's historical spread. Every processed OnTick quote is exported
incrementally. Python uses that same stream and the unchanged H01 M5 OHLC
stop-first reference. The generated Bid OHLC also matches the separately
exported broker H1 bars exactly. This validates implementation agreement under
the declared model; actual historical spreads and real-tick execution remain
unvalidated.

The bounded UTC+2 conversion was independently checked before the performance
run. Its hourly-return correlation with the existing public UTC H1 feed is
0.999596 across 636 aligned pairs; neighboring hour offsets are near zero.
All six weekly checks pass the thresholds registered before comparison.
This is empirical clock evidence for this interval, not an official broker
DST policy or authorization to reuse the offset across other dates.

The first February run uncovered an EA export defect. Entry timestamps were
valid while enumerating their native history records, but a later getter
returned zero with error 4755. The exporter now snapshots checked deal fields
while the record is available, and rejects missing or impossible timestamps.
The same deterministic receipt audit failed before this fix and passed after
it. All final timestamps, directions and prices were independently reconciled
against the tester journal. Diagnostic instrumentation is absent from the
current EA; its failing attempt remains archived.

The pass rule compares entry/exit M5 bars, direction and exit reason. It does
not require identical fill prices: entry prices match exactly, while the
largest exit-price difference is 0.030714 price units, reflecting native
rounding/tick fills versus the conservative M5 model. All differences remain
in the trade comparison. This window had one winner and four losses; native
price P&L before fees and account-currency rounding was **-$0.0592**. A code
comparison pass does not establish profitability.

The EA is restricted to the Strategy Tester. The simulated deposit is $20
USD with 1:100 leverage and 0.01 oz exposure. This does not reproduce the
online account's USC reporting, leverage or fees. Native stop/target execution
was exercised, but restart recovery and a nonzero equity drawdown halt were
not validated. The optional drawdown halt remains zero to preserve H01's
frozen schedule. No Step 9 forward run or live deployment follows from this
result. The previous V1/V2/H01 research and original online demo scripts remain
intact; their preservation checks are saved with the run.

H01's missing Step 7 remains a separate blocker. The consumed V1/V2 holdout
results cannot be transferred to H01 or called fresh validation. This run did
not read or reset those holdout data.

To run a new engineering attempt, then collect after MT5 finishes:

```sh
.venv/bin/python -m goldnix_step8_h01.native --config goldnix_step8_h01/continuation_decision.json
PYTHONPATH=goldnix:. .venv/bin/python -m goldnix_step8_h01.ea_parity
.venv/bin/python -m goldnix_step8_h01.audit_receipt
PYTHONPATH=goldnix:. .venv/bin/python -m goldnix_step8_h01.verify_run
.venv/bin/pytest -q goldnix_step8_h01/test_parity.py
```

The launcher disables online trading and runs the tester. After collection,
restore the online terminal with trading disabled and reconcile the account;
that restoration was completed for the saved final run. Frozen run artifacts
cannot be overwritten by the collector or analysis command.

See the [source research](../docs/GOLDNIX_STEP8_CONTINUATION_RESEARCH_20261112.md)
and [original zero-trade attempt](out/S8_20261112T152435Z/RESULT.json) for context.
