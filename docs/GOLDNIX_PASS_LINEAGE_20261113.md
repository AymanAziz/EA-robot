# Why the previous pass does not qualify the current M1 EA

**The old H01 Step 6 numerical PASS is real and still reproduces. There is no
saved result showing that H01 or the current M1 P01 passed both Steps 6 and 7.**
The user's approval to perform Step 7 has been received. The remaining block is
evidence, not permission.

## Which result belongs to which method

| Candidate | Actual method | Step 6 | Step 7 |
| --- | --- | --- | --- |
| V1 | Original frozen H1 strategy | NOT_TRADEABLE_AT_THIS_ACCOUNT_SIZE | Collapse check PASS, 60 trades; mean −0.16244 R |
| V2 | Separate frozen H1/H4 strategy | INSUFFICIENT_DATA | Collapse check PASS, 28 trades; mean +0.01973 R |
| H01_S11_M5_REPLAY | H1 channel20 entries, M5 execution, fixed SL/TP | All nine original numerical gates PASS | No matching result |
| M1_PROFIT_PROTECTION_P01 | M1 channel20 entries, one-second profit protection | Not qualified; short diagnostic sample negative | Preflight blocked |

Step 7 checks collapse relative to a strategy's own training result. It is not
an independent positive-profit requirement: V1's negative holdout mean still
met its declared collapse threshold. Neither V1 nor V2 had Step 6 approval.
Their Step 7 PASS cannot be assigned to H01, and H01's Step 6 PASS cannot be
assigned to M1 P01. Combining those unrelated passes would be false evidence.

Original records:

- [H01 Step 6](../goldnix_mtf2/out/H01_S11_M5_REPLAY/RESULT.json).
- [V1/V2 Step 7](../goldnix_step7/out/RESULT.json).
- [Current M1 comparison](../goldnix_p02/README.md).
- [Authorized P01 Step 7 preflight and M1 status](../goldnix_p01/step67/out/APPROVED_S7_M1_20261113T073520Z/REPORT.md).

## What was verified again

The original H01 records were preserved. This audit verified 160 artifact
hashes and 144 unchanged source hashes, checked all 1,025 entry timestamps and
directions against the original S11 records, and validated all 800 baseline
schedules for overlap, daily-halt and direction-count constraints.

Using the preserved trade and baseline lists, the original 10,000 monthly
bootstrap resamples and 100,000 annual Monte Carlo paths were rerun with the
same seeds and thresholds. Results match to floating-point tolerance:

| H01 metric | Reproduced value |
| --- | ---: |
| Trades | 1,025 |
| Mean R | +0.1201305124 |
| One-sided mean lower bound | +0.0385328919 R |
| Edge over matched random baseline | +0.3748477937 R |
| Edge lower bound | +0.2973956515 R |
| Profitable eras | 4 / 4 |
| Annual simulated p99 drawdown | $1.01222443 |
| Original drawdown limit | $2.40 |
| Original numerical gate verdict | PASS |

This is a recomputation from frozen trade records, not a fresh full price-path
simulation. G8/G9 retain their recorded values with verified source/artifact
hashes; native ATR and execution-sensitivity runs were not repeated. Historical
trading approval remains false. The selection-adjusted lower bound is still
−0.052164 R, only 26 trades occur in 2021–2025, and historical target-broker
costs remain unverified. These limits were already disclosed with the old pass.

## Why the current strategy is different

The channel period is 20 in both versions, but H01 uses 20 **hours**, while P01
uses 20 **minutes**. ATR, entry opportunities and trade durations therefore
change. H01 uses the original bid/ask OHLC midpoint construction; P01 constructs
its midpoint bars from quote events. The current EA also adds actual-entry risk
checks, daily attempt and equity guards, broker-session closes, a Malaysia risk
day, and profit-floor exits. Identical channel length and stop/target multiples
do not make these the same algorithm.

H01 used 2005–2025 public H1/M5 history. P01's current numerical comparison uses
generated broker quotes for January, February and March 1–14, 2024. The periods
and execution models differ, so comparing their total returns does not isolate
a timeframe effect. The audit found no changed gate threshold or corrupted
H01 result that explains the different statuses.

An EA attached to an M1 chart can explicitly read H1 data. That would preserve
H1 signal frequency only if its code does so; changing the displayed chart
cannot convert the current hard-coded M1 implementation back into H01.

## Profit-protection control on identical M1 inputs

One diagnostic control was registered before the new runs: turn off profit
protection and preserve every other input and execution rule. All three existing
M1 windows were evaluated. This is not a parameter search or a deployable new
candidate. February's control result was already known and was reproduced.

| Net USC | Protection ON | Protection OFF |
| --- | ---: | ---: |
| January 2024 | −15.30 | −45.48 |
| February 2024 | −11.81 | −9.55 |
| March 1–14, 2024 | +8.21 | +7.16 |
| Total | **−18.90** | **−47.87** |

Protection reduced total modeled losses by 28.97 USC on these observations,
although February worsened. Exits affect later position availability and daily
halts, so the populations differ: 318 protected trades versus 213 control
trades. Removing protection does not restore the old H01 strategy or make the
observed M1 total profitable. The active protective EA was not changed.

## What can honestly be approved

The original H01 numerical Step 6 pass is confirmed. Full H01 validation still
needs its own untouched subsequent Step 7 observations and resolution of its
disclosed execution/selection limits. Jan–Sep 2026 has already been consumed;
October/November has also been examined. These cannot be reused as fresh
holdout evidence. No new holdout price payload was read in this audit.

Keeping true M1 signals means qualifying P01 separately: full executable
Bid/Ask coverage, its own matched baseline and unchanged gates. A failed short
sample is not repaired by marking a field `approved`, changing random seeds,
lowering thresholds or combining certificates from different candidates.

For continued work the earlier H01 method is the verified historical reference.
No strategy replacement was deployed during this diagnosis. The user was asked
whether H1 signals on an M1 chart are acceptable; no response had arrived when
this report was written. Current demo P01 v1.20 remains active with protection.

The remaining Step 7 data requirement cannot be made complete by an immediate
rerun. A prospective interval must be registered before it starts, with a fixed
candidate, execution contract and evaluation endpoint; its result can then be
assessed once. No new period or automatic future evaluation was silently created.

Local reproducible diagnosis artifacts are in
[`var/goldnix_lineage_audit_20261113/`](../var/goldnix_lineage_audit_20261113/):
the H01 reproduction script/receipt, registered M1 control plan, control replay
script, all three control trade lists, results and SHA-256 manifest. The scripts
refuse to overwrite their result receipts. Generated artifacts remain local.
