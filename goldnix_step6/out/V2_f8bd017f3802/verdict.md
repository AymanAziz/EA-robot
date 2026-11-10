# V2: corrected Step 6

Evaluation: COMPLETE

Verdict: **INSUFFICIENT_DATA**

| Gate | Pass | Value | Requirement |
| --- | --- | --- | --- |
| G1 | False | -0.061685104557249154 | > 0.0 |
| G2 | True | 0.11295433679339598 | >= 0.1 |
| G3 | True | 0.024181278326578466 | > 0.0 |
| G4 | False | 2 | >= 3 |
| G5 | False | 677 | >= 1000 |
| G6 | True | 0.0014771048744460858 | <= 0.1 |
| G7 | False | 90.67403571428618 | <= 2.4 |
| G8 | True | 1.4218009478672966 | <= 8.0 |
| G9 | True | True | passed |

Baseline: 200 independent seeded MCMC chains targeting uniform schedules
conditioned on the same long/short counts, one-position rule and daily halt.
Finite burn-in approximates this conditional distribution; see diagnostics.
Sampler warning: False.
Signal/baseline confidence bounds use identical sampled calendar months.
Previous strategy trades reproduced exactly. No holdout was read.
