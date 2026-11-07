# XAU/USD USD 20 weekly-target result

Run on 2026-11-07 from the strategy preregistered in commits `2ecfbd5` and
`ccfcc6a`, before either holdout result was inspected. No broker credential was
read, no order was submitted, and XAU/USD remains outside the trading engine.

## Verdict

**Fail. This method did not meet the condition of more than USD 20 average net
profit per week.** It lost money in both untouched chronological tests, even
under the optimistic 5% financing sensitivity.

| Metric | Test A: 2022 | Test B: 2023 | Required |
| --- | ---: | ---: | ---: |
| Complete weeks | 52 | 52 | At least 52 |
| Mean net P/L per week | **-USD 12.68** | **-USD 14.41** | Above USD 20 |
| One-sided 95% lower mean | -USD 43.29 | -USD 31.22 | Above USD 20 |
| Total net P/L | -USD 659.57 | -USD 749.08 | Above USD 1,040 |
| Profitable weeks | 25 (48.1%) | 23 (44.2%) | Reported, not a gate |
| Weeks above USD 20 | 21 (40.4%) | 15 (28.8%) | Mean/confidence gates apply |
| Weekly profit factor | 0.784 | 0.596 | Above 1.0 |
| Maximum drawdown | -10.71% | -12.20% | No worse than -10% |
| Maximum absolute notional | USD 10,908.41 | USD 7,006.89 | At most USD 10,000 |
| Overall status | Fail | Fail | Both must pass |

The primary calculation charged one full reported spread per transaction,
2 bps slippage and 1 bp commission per side, plus a synthetic 10% annual
financing debit on absolute prior-close notional. The development-only spread
fallback was USD 0.300.

The lower 5% financing sensitivity also failed:

- Test A: -USD 6.30 average per week and -USD 327.86 total.
- Test B: -USD 10.72 average per week and -USD 557.21 total.

This shows the failure was not caused only by the deliberately conservative
10% financing assumption.

## Reproduction and evidence

- Data: 955 private D1 rows in 37 verified 31-day-or-shorter chunks, covering
  2020-12-01 through the last available bar on 2023-12-29.
- Frozen specification SHA-256:
  `39ef39fd0ceae6230730c335e82d7d57fce8a680d2fb2e5ac76571847e9c8510`.
- Prepared data SHA-256:
  `9941dc905de9822859649cb5183420375f01bb2aebcc793b0d1aef59f002dc21`.
- Internal report SHA-256:
  `32d570a036970f5ccdcf6968db427e72509cb09b0afbe512a3beb8d5573f06ec`.
- Initial run plus three cache-only reruns had identical file SHA-256:
  `a1eb9dab5e4878eac577e97ad6752a0d978a1c77e9a6f632deac07449476bdd4`.

Repeated calculation proves determinism only. It does not create four
independent market tests.

## Decision

No trade was placed. Searching more parameters or strategies on these same
2022/2023 holdouts until one reports a profit would convert them into
development data and manufacture a backtest result. That would be the
hallucinated proof this test was designed to prevent.

The result is historical research from an unidentified “Exness-style” MT5
feed, not OANDA, not a broker paper fill, and not evidence of future weekly
profit. The raw cache and full deterministic JSON report remain private under
`var/gold_weekly/` and are ignored by Git.

The method, assumptions, primary sources and limitations are documented in
[GOLD_WEEKLY_TARGET_RESEARCH.md](GOLD_WEEKLY_TARGET_RESEARCH.md).
