# V1: corrected Step 6

Evaluation: COMPLETE

Verdict: **NOT_TRADEABLE_AT_THIS_ACCOUNT_SIZE**

| Gate | Pass | Value | Requirement |
| --- | --- | --- | --- |
| G1 | False | -0.09642356731844724 | > 0.0 |
| G2 | False | 0.09943288567399441 | >= 0.1 |
| G3 | True | 0.04309296910208051 | > 0.0 |
| G4 | False | 0 | >= 3 |
| G5 | True | 1734 | >= 1000 |
| G6 | True | 0.002306805074971165 | <= 0.1 |
| G7 | False | 160.21199642857096 | <= 2.4 |
| G8 | True | 1.5037593984962405 | <= 8.0 |
| G9 | True | True | passed |

Baseline: 200 independent seeded MCMC chains targeting uniform schedules
conditioned on the same long/short counts, one-position rule and daily halt.
Finite burn-in approximates this conditional distribution; see diagnostics.
Sampler warning: False.
Signal/baseline confidence bounds use identical sampled calendar months.
Previous strategy trades reproduced exactly. No holdout was read.
