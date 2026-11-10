# Step 6 completed

Source commit: `2b5e1af`. Both evaluations finished, all nine gates were
computed, and both source/artifact freezes verified. The original V1 freeze
still validates. Original V1/V2 source, config, and results are unchanged.
Step 7 was not run and no holdout was opened.

| Gate | V1 | V2 | Requirement |
| --- | ---: | ---: | --- |
| G1 mean R lower bound | -0.096424 FAIL | -0.061685 FAIL | > 0 |
| G2 signal minus baseline | +0.099433 FAIL | +0.112954 PASS | >= +0.10R |
| G3 edge lower bound | +0.043093 PASS | +0.024181 PASS | > 0 |
| G4 positive eras | 0 FAIL | 2 FAIL | >= 3 |
| G5 baskets | 1734 PASS | 677 FAIL | >= 1000 |
| G6 gap-risk share | 0.2307% PASS | 0.1477% PASS | <= 10% |
| G7 one-year p99 drawdown | $160.21 FAIL | $90.67 FAIL | <= $2.40 |
| G8 fill-policy delta | 1.5038 pp PASS | 1.4218 pp PASS | <= 8 pp |
| G9 ATR parity | PASS | PASS | passed |

V1 verdict: **NOT_TRADEABLE_AT_THIS_ACCOUNT_SIZE**.
V2 verdict: **INSUFFICIENT_DATA**, also failing G1/G4/G7.

The corrected G3 passes for both studies. This does not establish positive
net mean R with confidence (G1), nor account feasibility (G7). V1's G2 remains
below its threshold; rounding its estimate to +0.10R would be misleading.

Artifacts:

- [V1 report](V1_4b823fa2ca89/verdict.md), [metrics](V1_4b823fa2ca89/metrics.json),
  [freeze](V1_4b823fa2ca89/FROZEN.yaml).
- [V2 report](V2_f8bd017f3802/verdict.md), [metrics](V2_f8bd017f3802/metrics.json),
  [freeze](V2_f8bd017f3802/FROZEN.yaml).
- [Verbatim tests and lint](test_output.txt); [independent review findings and fixes](REVIEW.md).

Both studies used 200 baseline schedules per era, 10,000 monthly bootstrap
resamples and 100,000 one-year drawdown paths. Every generated baseline schedule
passed overlap, daily-halt and matched direction-count checks. Strategy trade
lists reproduced the original studies exactly. No sampler warnings were
triggered in any era. Finite MCMC sampling remains approximate; its diagnostics
do not prove convergence. The method and limitations are documented in
[the evaluation README](../README.md).

Validation: 110 tests passed; Ruff passed; all original and revised freeze
checks passed. Runtime: Python 3.12.16, NumPy 2.5.4, pandas 2.3.3,
PyYAML 6.0.3, pytest 9.2.0.

There is no pending Step-6 calculation in this revision. Completion records
the actual verdict; it does not convert failed gates into approval.
