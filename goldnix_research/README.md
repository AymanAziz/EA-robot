# Goldnix replacement research — 2026-11-12

**Outcome: no Step 6 pass established.** The study ran 24 registered candidates
and a separately registered, explicitly adaptive four-candidate risk-budget
follow-up. None cleared the profitability-confidence screen. All outcomes,
including failures, are retained. V1/V2 and their completed Step 7 results are
unchanged. No orders were placed and no account was opened or funded.

## What was tried

The first [protocol](protocol.json) was saved before its first backtest. It
declared eight configurations per family, actual historical bid/ask spreads,
the original execution engine and the original four era boundaries:

| Family | Fixed candidate grid |
| --- | --- |
| Aroon controls | Period 35/70, crossing threshold 25/50, stop 1/2 ATR, target twice stop |
| Trend/pullback | EMA100/200, RSI(2) recovery from 10/20, stop 1/2 ATR, target twice stop |
| Channel breakout | Prior 20/55-bar range, stop 1/2 ATR, target twice/three times stop |

The channel definition emits a BUY for every closed price above the previous
N-bar high, or a SELL below the previous N-bar low. The current bar is excluded
from channel construction. This is the registered implementation's repeated
new-extreme convention, not the crossing-event convention proposed as an
alternative in the research note. One-position and daily-halt rules prevent
overlapping strategy baskets. No intrabar entry at a retrospectively known
channel level is assumed.

Pullback RSI uses exponentially smoothed gains/losses with alpha 1/2,
`adjust=False`, initialized from the first available change, and two required
changes. EMA uses `adjust=False`; its 1,000-bar warm-up is excluded from trading.
Flat gains/losses generate no recovery signal. Other families use 100 warm-up
bars. The identical Aroon70/50, one-ATR control reproduced the frozen V1 trade
timestamps, directions and R values exactly.

Public interfaces tested: candidate preparation (including future-data
invariance), calendar-month screening, fixed-trade spread accounting, and
nominal-risk eligibility. These extend the already authorized signal,
simulation and statistical boundaries. The frozen execution engine is reused.

## Screening results

Screening used 10,000 calendar-month bootstrap resamples, including empty
calendar months, with a fixed seed. All candidates were also run with
stop-first and target-first fill policies. Screening applies the original G1,
G4, G5, G6 and G8 thresholds; it is not a complete G1–G9 evaluation.

| Candidate | Baskets | Mean R | 5% mean lower bound | Positive eras |
| --- | ---: | ---: | ---: | ---: |
| C07: original V1 control | 1,734 | -0.039752 | -0.096367 | 0/4 |
| C20: 20-bar channel, 2 ATR stop, 6 ATR target | 3,926 | +0.038357 | -0.000098 | 4/4 |
| C24: 55-bar channel, 2 ATR stop, 6 ATR target | 2,550 | +0.046025 | -0.003578 | 4/4 |

The best preliminary lower bound is negative; rounding it to zero or changing
the seed would not establish a pass. This screening bootstrap draws its own
monthly samples. Full corrected Step 6 uses paired monthly/baseline resampling,
so finite Monte Carlo estimates can differ slightly even for the same trade
list (as the control shows). A borderline screen is not a definitive economic
conclusion, and no full baseline was selected under the registered rule.

The extra 24-trial selection-adjusted lower bounds are -0.026230R for C20 and
-0.039827R for C24. Their .05/24 bootstrap tail has only about 21 nominal tail
draws; treat its precision accordingly. This correction covers the registered
family only, not V1/V2, prior sensitivities, or all adaptive research decisions.

All 24 configurations and results are in
[the screening summary](out/screen/SUMMARY.json). Trade lists and per-era
results are saved under `out/screen/Cxx/`. The exact source and protocol used
are copied into `out/screen/source/`; later source changes do not replace that
record.

## Risk and cost diagnostics

C20 and C24 were selected after screening for additional accounting diagnostics,
not promoted to approved strategies. Each risk calculation uses 100,000 IID
one-year paths at the observed annual trade rate and the original fixed seed.

| Candidate | Annual p99 DD at current 1 oz | Conditional DD at 0.01 oz | $20-account limit |
| --- | ---: | ---: | ---: |
| C20 | $518.96 | $5.19 | $2.40 |
| C24 | $415.37 | $4.15 | $2.40 |

At unchanged P/L distributions, maximum exposure for this risk limit would be
approximately 0.004625 oz and 0.005778 oz respectively. Neither exposure is
available on the currently verified 1 oz-minimum MetaQuotes contract. The
0.01 oz comparison uses a published HFM product specification, not an actual
qualified account. It still fails this conditional risk screen for both leads.

Fixed-trade spread credits of 0%, 25%, 50%, 75% and 100% were examined as
accounting scenarios. A 25% credit makes both leads' raw confidence bounds
positive; within the initial 24-trial correction, C20 needs a 50% credit and
C24 needs 75% among those sampled scenarios. These are not executable costs,
new backtests or Step 6 passes. Different spreads can change eligibility,
fills and baseline returns; no such change was assumed to be verified.
The full diagnostics are in [COST_DIAGNOSTICS.json](out/COST_DIAGNOSTICS.json).

## Separately recorded risk-budget follow-up

The first 24-candidate study ended with no selected candidate. After its risk
diagnostics, the [follow-up protocol](risk_protocol.json) registered four new
variants: C20/C24 with nominal per-trade risk capped at 0.5% or 1% of $20,
assuming the documented 0.01 oz product exposure. This is adaptive research;
it is not described as an untouched pre-registration or an independent trial.
The running count is 28 candidates plus earlier project trials.

Eligibility uses the closed signal bar's ATR and ask-minus-bid spread. It
filters both the strategy signal and the direction-eligible opportunity set
that a future baseline would have to match. Next-open spread changes and gaps
can exceed this nominal risk estimate; it is not a guaranteed loss cap.

| Candidate | Parent / nominal cap | Baskets | Mean lower bound | Positive eras | Conditional p99 DD at 0.01 oz |
| --- | --- | ---: | ---: | ---: | ---: |
| R01 | C20 / 0.5% | 3,109 | -0.013750 | 3/4 | $3.18 |
| R02 | C20 / 1% | 3,787 | -0.008201 | 3/4 | $4.46 |
| R03 | C24 / 0.5% | 1,932 | -0.050673 | 3/4 | $2.66 |
| R04 | C24 / 1% | 2,454 | -0.018317 | 3/4 | $3.62 |

None clears G1 or the conditional G7 scenario. No further risk-cap thresholds
were searched. The [follow-up summary](out/risk_screen/SUMMARY.json) includes a
28-trial adjusted bound and its exact source snapshot. Earlier phase outputs
retain their originally declared 24-trial adjustment.

## Meaning and remaining evidence

This work found useful improvements in trade count and per-era point means,
but no reliable net edge or qualifying Step 6 candidate. G2/G3 were not run for
these rejected candidates. It would be incorrect to call the uncomputed gates
passes, to overwrite the old verdicts, or to call a same-history selected result
independent approval.

The next empirical requirements are a verified smaller-contract account,
actual target-venue bid/ask history and fee terms, and a new validation design.
The original $20 balance is retained. No proposed deposit or fictitious account
equity is used to manufacture a risk pass. The opened 2026 holdout was not read
or reused by either new experiment.

Primary-source findings and their limitations:

- [Small-contract broker investigation](../docs/GOLDNIX_SMALL_CONTRACT_RESEARCH_20261112.md).
- [Signal-family research](../docs/GOLDNIX_SIGNAL_RESEARCH_20261112.md).

## Verification and reproduction

Actual verification output:

```text
162 passed in 3.90s
All checks passed!
```

Full [test output](out/test_output.txt) is saved. This is a software test result,
not a trading-strategy pass. Original and corrected freezes and the completed
Step 7 artifacts are independently rechecked in the final verification record.

The experiment commands refuse to overwrite existing outputs:

```sh
PYTHONPATH=.:goldnix .venv/bin/python -m goldnix_research.screen
PYTHONPATH=.:goldnix .venv/bin/python -m goldnix_research.costs
PYTHONPATH=.:goldnix .venv/bin/python -m goldnix_research.risk_budget
```

Reproduction of phase 1 must use its saved source snapshot because the current
screen function gained a preparation hook for phase 2 after phase 1 finished.
That hook's default preserves the original behavior. Do not delete evidence
or reuse these commands to search new seeds.

Data source: EV Trading Labs (https://evtradelabs.com/data). Quotes remain local
and are not republished in this report. Historical fills remain the original
spread-based H1 research model; commissions, financing, market impact and exact
tick paths have not silently become verified.
