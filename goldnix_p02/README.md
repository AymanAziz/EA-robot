# Step 6 entry-filter comparison — 13 November 2026

**Step 6 has not passed. No candidate met the preregistered improvement screen.**
The research batch is complete; the full four-era qualification is blocked by
missing executable quote history and a certified matched random baseline.
The original P01 EA remains deployed. Step 7 was not run and requires the
user's later explicit approval.

## What was tested

Four filters were registered before evaluating their returns: completed M15
trend, completed H1 trend, both trends, and both trends plus a strong M1 candle
close. Trend uses midpoint EMA20 on M15 and EMA50 on H1, with three-bar slope.
Each timeframe needs 100 complete bars. Missing minutes invalidate the higher
candle; forming or stale candles cannot supply an entry direction. BUY and SELL
rules mirror each other. P01 sizing, SL, TP, profit protection and risk guards
are unchanged.

All four filters were compared over January, February and March 1–14, 2024,
using generated MT5 broker quotes and recorded timer events. Dates are broker
UTC+2 calendar boundaries. Each window starts a separate 2,000 USC simulated
account; pooled results are research observations, not a continuous account run.
December 2023 and preceding evaluation windows provide untraded indicator
history. Only bars strictly earlier than the evaluation window are accepted.

The first screen started indicators cold at each month boundary. That result
is retained in [cold_start.json](evidence/cold_start.json). A committed
[warmup revision](warmup_revision.json) required preceding history, and all
four candidates were rerun without changing parameters, windows or the
improvement criteria. The results below come from that corrected comparison.

## Corrected results

`COMMON_P01` applies the same higher-timeframe readiness requirements as the
filters, without a directional filter. It isolates the effect of direction
from data availability. The unfiltered original is also retained, because that
is the EA the user already has.

| Strategy | Trades (BUY / SELL) | Mean R | Net USC | Annual simulated p99 drawdown, USD |
| --- | ---: | ---: | ---: | ---: |
| Original P01 | 318 (156 / 162) | −0.03664 | −18.90 | 3.0334 |
| Common-readiness P01 | 314 (151 / 163) | −0.05670 | −29.68 | 3.5135 |
| M15 filter | 230 (111 / 119) | −0.18072 | −71.69 | 5.1760 |
| H1 filter | 217 (110 / 107) | −0.09721 | −47.26 | 4.0271 |
| M15 + H1 | 177 (91 / 86) | −0.04415 | −24.55 | 2.6977 |
| M15 + H1 + strong close | 156 (77 / 79) | −0.05514 | −22.40 | 2.4860 |

| Net USC by window | January | February | March 1–14 |
| --- | ---: | ---: | ---: |
| Original P01 | −15.30 | −11.81 | +8.21 |
| Common-readiness P01 | −13.87 | −24.27 | +8.46 |
| M15 filter | −41.38 | −33.28 | +2.97 |
| H1 filter | −28.96 | −43.24 | +24.94 |
| M15 + H1 | −7.04 | −31.15 | +13.64 |
| M15 + H1 + strong close | +0.82 | −30.67 | +7.45 |

The screen required higher mean R **and** net USC than COMMON_P01 in every
window, lower pooled p99 drawdown, and observations on both sides. Every filter
performed worse in February. Both combined filters reduced simulated drawdown,
partly by trading less, but neither beat the original P01's pooled return or
mean R. All candidates have a negative paired-month lower confidence bound
versus COMMON_P01. **No candidate is selected or deployed.**

Full numerical results, including per-window mean R and bootstrap statistics,
are in [preceding_history.json](evidence/preceding_history.json) and
[preceding_history.csv](evidence/preceding_history.csv). Both cold-start and
corrected outcomes are preserved with [hash provenance](evidence/provenance.json).

The original P01's earlier two-window result was −27.11 USC and −0.05025 R.
Its three-window result changes because March was added; this is not a code
improvement. Native/reference P01 engineering parity now covers 318 matching
trades and 72,136 matching signal decisions across the three windows.

## Qualification limits and remaining work

The 10,000 bootstrap resamples contain only three calendar blocks, with March
partial and the earlier months already examined. The 100,000 Monte Carlo paths
resample observed trades independently at each strategy's annualized frequency.
They are conditional simulations, not forecasts, and do not prove performance
through unobserved regimes. At least 82 earlier variants plus these four filters
have been considered; selection bias remains material.

Original gates G1–G9 remain unchanged. In particular:

- Mean-return lower confidence bounds remain negative in this screen.
- Each population is below 1,000 trades and lies entirely within era D.
- A certified 200-draw matched random baseline per era is still missing.
- Even the lowest candidate p99 drawdown, $2.486, exceeds the original $2.40
  cap for a $20 account.
- Generated ticks cannot establish full historical spread, gap, stop execution,
  swap or commission behavior. The fine-USC replay uses conservative target
  fills; the native parity comparator separately mirrors tester rounding.
- Full four-era data quality and execution-ambiguity checks remain unqualified.

The public Dukascopy M1 cache now contains 33 paired calendar days,
May 30–July 1, 2005: 27,039 observed minutes, 20,477 placeholders and four
unexplained zero-volume minutes. The resume stopped on HTTP 503 at July 2 BID;
no collector is left running. M1 candles alone cannot establish one-second
profit-management execution. The alternative HistData investigation found
no listed coverage before March 2009 and a systematic Bid/Ask schema conflict
in the downloaded sample; that archive is quarantined. See the
[data recovery report](../docs/GOLDNIX_STEP6_DATA_RECOVERY_20261113.md).

Completing formal Step 6 requires qualified 2005–2025 quote coverage, the
matched baseline, and a candidate meeting the unchanged gates. These results
do not justify another parameter sweep on the same short sample. Once suitable
data is available, any further hypothesis must be registered before evaluation.
Step 7 remains locked until the user approves it; no approval is inferred from
this research run. Previously examined 2026 history remains consumed.

## Verification and reproduction

83 related tests passed, including seven new filter/replay tests. They cover
closed-candle availability, stale data, missing-minute rejection, future-prefix
invariance, mirrored directions, preceding-history boundaries and exact P01
replay preservation. Ruff and whitespace checks passed. Both run manifests
verified: 33 cold-start artifacts and 36 corrected artifacts. The existing
Step 7 unit tests use fixtures and do not evaluate a holdout price dataset.

```sh
PYTHONPATH=goldnix:. .venv/bin/pytest -q goldnix_p02/tests goldnix_p01/tests goldnix_step6/tests goldnix_step7/tests
PYTHONPATH=goldnix:. .venv/bin/python -m goldnix_p02.evaluate --warmup goldnix_p01/out/P01N_20261113T071859Z
```

Evaluation requires the local quote/timer artifacts named in `evaluate.py`.
They are excluded from Git. The unfiltered fork was also checked against the
original replay on all three actual evaluation windows. Production EA and P01
source hashes remain unchanged from the pushed snapshot. A fresh terminal
inspection confirmed demo v1.20 connected, data ready, trading enabled, profit
protection enabled, and no audit halt after the native tester handoff.
