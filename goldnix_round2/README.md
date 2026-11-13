# GOLDNIX: second exploratory improvement round

S11 passes all nine unchanged numerical Step 6 gates only in the hypothetical 0.01 oz exposure scenario. At the verified 1 oz minimum it passes eight gates and fails G7, giving `NOT_TRADEABLE_AT_THIS_ACCOUNT_SIZE`. Approval remains false.

This round tested 24 new variants, bringing the recorded research registry to 52. S11 and S12 qualified for the full-evaluation shortlist. The registered selection rule chose S11 before its random-entry baseline was evaluated. All unsuccessful candidates are retained.

## Selected strategy

S11 enters on the next H1 bar after the closed midpoint price exceeds the previous 20-bar high or falls below the previous 20-bar low. It uses the existing simple ATR(14), a 2 ATR stop (minimum $0.50 price distance), and a target three times that distance. Stops and targets remain fixed.

Entry eligibility requires `(stop distance + signal-close spread) × 0.01 oz <= $0.05`, or 0.25% of the assumed $20 account. This is a nominal filter, not a guaranteed loss cap: next-open spreads and adverse gaps can exceed it. The same fixed signal filter is used when reporting the 1 oz exposure comparison. It does not enforce 0.25% risk on the verified account.

Original bid/ask quotes, spread ceiling, Friday flattening, holiday exclusion, one-position rule, daily loss halt, and pessimistic fill priority are preserved. No spread credit or changed gate threshold was used.

## Comparison with earlier work

| Candidate | Baskets | Mean R per basket | Positive eras | Annual p99 drawdown at 1 oz | Same path scaled to 0.01 oz |
| --- | ---: | ---: | ---: | ---: | ---: |
| Frozen V2 | 677 | 0.028248 | 2/4 | $90.67 | $0.91 |
| Previous research C20 | 3,926 | 0.038357 | 4/4 | $518.96 | $5.19 |
| New S11 | 1,025 | 0.120185 | 4/4 | $101.21 | $1.01 |

S11 improves mean return and drawdown relative to the last research candidate C20. Its drawdown is higher than frozen V2, while its trade count and era consistency are better. The 0.01 oz column is arithmetic exposure scaling using the same historical quotes; it does not establish an executable account or broker-specific performance.

## Full numerical gate evaluation

| Gate | Measure | Requirement | At verified 1 oz | At hypothetical 0.01 oz |
| --- | --- | --- | --- | --- |
| G1 | 0.038543 | > 0.0 | PASS | PASS |
| G2 | 0.377551 | >= 0.1 | PASS | PASS |
| G3 | 0.300537 | > 0.0 | PASS | PASS |
| G4 | 4.000000 | >= 3 | PASS | PASS |
| G5 | 1025.000000 | >= 1000 | PASS | PASS |
| G6 | 0.014634 | <= 0.1 | PASS | PASS |
| G7 | $101.212950 / $1.012129 | <= 2.4 | FAIL | PASS |
| G8 | 0.227790 | <= 8.0 | PASS | PASS |
| G9 | True | passed | PASS | PASS |

Random-entry mean: -0.257366R. Strategy minus random entries: 0.377551R, with a one-sided 95% paired-month lower bound of 0.300537R.

Each era has 200 independently seeded schedule chains with 20 sweeps per trade. All 800 saved schedules preserve the observed long/short counts, causal risk eligibility, quote-side fills, one-position constraint, and daily loss halt. None triggers the predeclared sampler warning; finite MCMC diagnostics do not prove convergence.

The full paired bootstrap uses 10,000 resamples and includes inactive months. Its G1 lower bound is 0.038543R. The preliminary screen lower bound was 0.036753R; the small difference comes from the paired bootstrap sampling baseline draws as well as months. Both implementations and seeds are saved. The drawdown estimate uses the unchanged 100,000 IID annual paths at the observed rate of 50 baskets per year.

## Remaining limitations

- The 52-trial adjusted screen lower bound is **−0.046556R**. Positive raw gates do not establish an edge after the search. This adjustment also excludes earlier V1/V2 work and sensitivities; the adaptive research history is broader than 52 trials.
- Only 26 trades occur in 2021–2025. There are 86 inactive calendar months across the study. Recent evidence is thin.
- No matching 0.01 oz account, historical target-venue spreads, margin, commission, financing, or execution slippage has been verified. Public contract specifications alone do not approve trading.
- The available 2026 holdout was already consumed by the frozen V1/V2 evaluation. This round never read or simulated it. S11 has no independent holdout result; future untouched observations are needed.
- The verified $20 account remains blocked by G7. Step 8 is not approved.

## Every new trial

| ID | Family | Period | Stop ATR | Reward ratio | Exit | Risk share | Baskets | Mean R | Raw lower R | 52-trial lower R | Positive eras | Scenario p99 USD |
| --- | --- | ---: | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| S01 | channel | 20 | 1 | 3 | break_even | none | 6683 | -0.058486 | -0.087661 | -0.113292 | 1 | 4.180635 |
| S02 | channel | 20 | 1 | 3 | trail | none | 6751 | -0.070179 | -0.098102 | -0.123805 | 1 | 4.125167 |
| S03 | channel | 20 | 2 | 3 | break_even | none | 4342 | 0.011522 | -0.018911 | -0.045360 | 3 | 5.203756 |
| S04 | channel | 20 | 2 | 3 | trail | none | 4530 | 0.003490 | -0.024942 | -0.049982 | 2 | 5.237786 |
| S05 | channel | 55 | 1 | 3 | break_even | none | 3873 | -0.027707 | -0.068546 | -0.100249 | 2 | 2.970508 |
| S06 | channel | 55 | 1 | 3 | trail | none | 3914 | -0.041766 | -0.080982 | -0.116087 | 1 | 2.902150 |
| S07 | channel | 55 | 2 | 3 | break_even | none | 2628 | 0.037522 | -0.005657 | -0.044658 | 3 | 3.879034 |
| S08 | channel | 55 | 2 | 3 | trail | none | 2676 | 0.025167 | -0.015312 | -0.051669 | 2 | 3.794480 |
| S09 | channel | 20 | 2 | 3 | fixed | 0.00125 | 5 | 1.002269 | -1.260292 | -1.260292 | 1 | 0.027114 |
| S10 | channel | 20 | 2 | 3 | break_even | 0.00125 | 5 | 1.002269 | -1.260292 | -1.260292 | 1 | 0.027114 |
| S11 | channel | 20 | 2 | 3 | fixed | 0.0025 | 1025 | 0.120185 | 0.036753 | -0.046556 | 4 | 1.012129 |
| S12 | channel | 20 | 2 | 3 | break_even | 0.0025 | 1078 | 0.071121 | 0.003510 | -0.055029 | 3 | 0.973198 |
| S13 | channel | 55 | 2 | 3 | fixed | 0.00125 | 3 | 2.471281 | 2.471281 | 2.471281 | 1 | 0.000000 |
| S14 | channel | 55 | 2 | 3 | break_even | 0.00125 | 3 | 2.471281 | 2.471281 | 2.471281 | 1 | 0.000000 |
| S15 | channel | 55 | 2 | 3 | fixed | 0.0025 | 568 | 0.134700 | 0.020900 | -0.090655 | 4 | 0.728844 |
| S16 | channel | 55 | 2 | 3 | break_even | 0.0025 | 574 | 0.092353 | -0.005853 | -0.096709 | 3 | 0.662929 |
| S17 | rejection | 20 | 1 | 1 | fixed | none | 8678 | -0.153232 | -0.171072 | -0.186549 | 0 | 4.754597 |
| S18 | rejection | 20 | 1 | 2 | fixed | none | 7684 | -0.127683 | -0.151613 | -0.172950 | 0 | 5.129947 |
| S19 | rejection | 20 | 2 | 1 | fixed | none | 6221 | -0.076165 | -0.095428 | -0.112672 | 0 | 6.192160 |
| S20 | rejection | 20 | 2 | 2 | fixed | none | 4519 | -0.087517 | -0.118235 | -0.148957 | 0 | 6.459288 |
| S21 | rejection | 55 | 1 | 1 | fixed | none | 4794 | -0.163540 | -0.187209 | -0.210179 | 0 | 3.339079 |
| S22 | rejection | 55 | 1 | 2 | fixed | none | 4367 | -0.152148 | -0.184913 | -0.212108 | 0 | 3.809793 |
| S23 | rejection | 55 | 2 | 1 | fixed | none | 3659 | -0.093304 | -0.117550 | -0.137864 | 0 | 4.793611 |
| S24 | rejection | 55 | 2 | 2 | fixed | none | 3282 | -0.103715 | -0.137997 | -0.165646 | 0 | 5.536157 |

## Validation and saved evidence

178 tests passed; Ruff passed. New tests cover causal stop management, both trade directions, adverse gaps, fixed-mode parity, rejection signals, future-data isolation, matched random schedules, and the separation of scenario results from account approval. Historical controls reproduced every trade column for V1 (1,734 baskets) and C20 (3,926 baskets).

Original V1/V2 sources and freezes, all 85 prior research manifest files, and Step 7 sources and artifacts were verified unchanged. The new source snapshots and each saved trade count and mean are authenticated in `out/VERIFICATION.json`; `out/MANIFEST.json` hashes the complete new research record.

- [Registered protocol](protocol.json)
- [All screening results](out/SUMMARY.json)
- [S11 complete evaluation](out/full_evaluation/RESULT.json)
- [S11 trades](out/S11/trades.csv)
- [Historical engine controls](out/CONTROLS.json)
- [Test output](out/test_output.txt)
- [Verification](out/VERIFICATION.json)

The runners create output directories exclusively and refuse to overwrite this evidence. Any later experiment needs a separately recorded protocol and output directory.
