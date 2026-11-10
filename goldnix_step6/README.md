# Completed evaluation versus approval

This revision evaluates the existing V1 and V2 settings and all original G1-G9
thresholds. It preserves earlier source/config/output and compares reproduced
strategy trade lists with the earlier artifacts. It does not optimise signals,
open the holdout, change account equity, or authorise trading.

## Corrections

- The old baseline sampled each trade independently, allowing overlaps and
  ignoring the daily halt. Here every schedule enforces both rules, while
  retaining each era's observed BUY and SELL basket counts. Candidates use the
  same static eligibility and single-trade fill logic. V2 also matches H4
  direction and positive valid spread eligibility.
- Sampling is uniform over **feasible fixed-count schedules**, not marginally
  uniform over every individual bar. Those are different distributions when
  trades overlap or halts apply. Independent seeded Metropolis chains target
  the conditional schedule distribution. Proposals use single replacement (80%),
  paired replacement (15%), or a complete independent schedule (5%). Replacements
  preserve direction counts; infeasible changes are rejected. Global proposals
  connect otherwise isolated feasible components. Forward/reverse proposal
  probabilities match, hence feasible schedules have equal stationary weights.
  The observed signal schedule is
  only an initial feasible state, not a privileged output candidate.
- Each of 200 independent chains uses 20 full replacement sweeps. This finite
  burn-in is an approximation to the stationary distribution. Reported checks
  compare midpoint/final means and starting-schedule retention. They cannot
  prove convergence. A sampler warning prevents interpreting
  a numerical PASS as validated approval. The original nine gate thresholds
  are unchanged; this warning concerns numerical reliability.
- Signal and baseline use the same sampled calendar months for the edge
  bootstrap, with 10,000 resamples and one-sided 5% lower bounds. Empty calendar
  months are retained. Each replicate also resamples the 200 baseline draw IDs
  and averages their monthly-resampled means, targeting the declared mean random
  baseline and its Monte Carlo uncertainty. Resamples containing zero signal or
  baseline baskets are rejected and counted explicitly.
- Reference win rates average spread/stop ratios at trade level, which agrees
  with the trade-level mean R definition. They assume fixed stop/target outcomes
  and are not exact for Friday closes or gaps.

## Risk and remaining model limitations

G7 retains the declared 100,000 IID one-year Monte Carlo paths, observed trade
rate, actual price-unit P/L at 0.01 standard lot, USD 20 account, and 12% limit.
This is not a margin-aware equity simulation or a model of unseen tail events.
MAE/MFE are inherited H1 bar-range approximations; exit-bar extremes can include
price movement after the modelled exit. They are reported but do not gate.
G9 relies on the recorded broker ATR parity evidence and unchanged ATR code;
it does not assert EA execution parity or H4 broker-data parity.
Commissions, financing and slippage beyond the specified spread/gap model are
not introduced silently. This remains the original spread-based research test.

## Artifacts and freeze

Each study produces `metrics.json`, `verdict.md`, signal trades, compressed full
baseline trades, draw summaries, sampler diagnostics, config/protocol copies,
  and `FROZEN.yaml`. A freeze is written for a completed failed verdict as well
as a completed pass. It records the code commit, source and artifact hashes,
configuration and verdict. Verification checks hashes and refuses overwrites.
Execution refuses research sources that differ from the recorded commit.
All corrected and imported source files are included in the manifest. Old
V1/V2 freezes are never overwritten. Strategy development on already examined
data remains exploratory and cannot become independent validation by passing
this numerical report.

```sh
PYTHONPATH=.:goldnix .venv/bin/pytest -q goldnix/tests goldnix_v2/tests goldnix_step6/tests
PYTHONPATH=.:goldnix .venv/bin/python -m goldnix_step6.runner --study V1
PYTHONPATH=.:goldnix .venv/bin/python -m goldnix_step6.runner --study V2
```

The runner refuses to overwrite an existing run with the same source/data hash.
