# GOLDNIX: actual-exposure feasibility and third research round

Step 6 remains FAIL on the existing $20 MetaQuotes demo account. All 16 newly registered tight-stop variants failed G1 and G7 at the actual 1 oz minimum. The previous S11 candidate is retained; no frozen strategy or previous result was replaced.

## Refreshed account evidence

The existing read-only MT5 exporter ran on 2026-11-12. Automated trading was disabled; no orders were sent. Only the XAUUSD gold contract was exported from the current server. The source CSV and exporter are preserved in `venue/`.

| Account property | Observed value |
| --- | ---: |
| Equity / free margin | $20.00 / $20.00 |
| Minimum XAUUSD volume / volume step | 0.01 lot / 0.01 lot |
| Contract size | 100 oz per lot |
| Minimum price-move exposure | $1 loss per $1/oz adverse move = 1 oz |
| BUY / SELL minimum margin | $39.80 / $39.79 |
| Quoted spread at export | $0.13/oz |

The minimum order needs more margin than the account has. This is an execution constraint separate from the nine historical statistical gates. The prior $41.17 margin observation is superseded by this fresh snapshot, while the 1 oz minimum remains unchanged. This snapshot is not historical execution-cost evidence.

## Registered experiment

The protocol was written before simulation. It tests 20- and 55-bar channel entries, stop multipliers of 0.05/0.10/0.25/0.50 ATR, and target-to-stop ratios of 2 or 3: 16 variants, bringing the explicit registry to 68. The original $0.50 price-distance floor, bid/ask quotes, spread ceiling, Friday rules, daily halt, and fill policies are unchanged.

The selection rule requires passing preliminary gates at the verified 1 oz exposure. No candidate qualified, so no full random-entry baseline was run for these failures. G2/G3 remain explicitly unevaluated. A hypothetical smaller-exposure result cannot qualify a candidate in this round.

| ID | Channel | Stop ATR | Target / stop | Baskets | Mean R | Raw lower R | p99 DD at 1 oz, USD | Fill delta, pp |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| T01 | 20 | 0.05 | 2 | 7921 | -1.305016 | -1.344973 | 282.34 | 65.773 |
| T02 | 20 | 0.05 | 3 | 8008 | -1.190705 | -1.235275 | 269.84 | 56.881 |
| T03 | 20 | 0.1 | 2 | 8162 | -1.240022 | -1.274835 | 310.57 | 61.179 |
| T04 | 20 | 0.1 | 3 | 8242 | -1.122618 | -1.162059 | 296.11 | 50.253 |
| T05 | 20 | 0.25 | 2 | 9214 | -0.787057 | -0.818608 | 422.18 | 30.423 |
| T06 | 20 | 0.25 | 3 | 9088 | -0.666583 | -0.703239 | 380.20 | 19.254 |
| T07 | 20 | 0.5 | 2 | 9459 | -0.314904 | -0.340626 | 444.59 | 7.400 |
| T08 | 20 | 0.5 | 3 | 8620 | -0.263565 | -0.296342 | 401.99 | 3.819 |
| T09 | 55 | 0.05 | 2 | 4901 | -1.309292 | -1.351996 | 180.30 | 65.642 |
| T10 | 55 | 0.05 | 3 | 4954 | -1.187280 | -1.236378 | 172.87 | 55.885 |
| T11 | 55 | 0.1 | 2 | 5057 | -1.232839 | -1.269977 | 201.87 | 60.105 |
| T12 | 55 | 0.1 | 3 | 5100 | -1.108703 | -1.151790 | 192.36 | 48.922 |
| T13 | 55 | 0.25 | 2 | 5661 | -0.758282 | -0.790638 | 279.94 | 28.917 |
| T14 | 55 | 0.25 | 3 | 5587 | -0.630788 | -0.669960 | 256.15 | 18.633 |
| T15 | 55 | 0.5 | 2 | 5698 | -0.288204 | -0.318214 | 306.16 | 7.153 |
| T16 | 55 | 0.5 | 3 | 5179 | -0.220981 | -0.261009 | 274.30 | 3.537 |

The lowest new p99 drawdown is $172.87, still far above $2.40 and worse than S11’s $101.21. Every new mean is negative (−1.309R to −0.221R). Twelve of the sixteen violate the 8-percentage-point fill-policy limit, demonstrating that hourly bars cannot reliably establish the order of tight stop/target hits. More optimistic fills cannot be used as a pass.

## Analytic check of the risk failure

The new risk check computes the probability of a sufficiently long run of losses under the same empirical IID annual model as G7. If each loss is at least `L`, a consecutive run with total loss strictly greater than $2.40 necessarily breaches the drawdown limit. A finite-state recurrence calculates the probability of such a run; the largest separate bound is retained, without incorrectly adding correlated probabilities.

For S11, 62.24% of recorded trades lose at least $2.84793 at 1 oz. A single such loss exceeds the $2.40 limit. At 50 trades per year, the probability of at least one such loss is `1 - (1 - 0.622439)^50`, well above 99.99%. The saved floating-point calculation rounds this to 1.0; that is numerical rounding, not a claim of logical certainty.

Every new tight-stop variant also has a loss-run lower bound above 99.99% under its recorded empirical distribution and annual rate. Changing the Monte Carlo seed cannot credibly repair these risk failures. This result applies to the evaluated distributions and the existing IID model; it is not a proof that every conceivable gold strategy must fail.

## What is still required

S11 already passed all nine raw numerical checks only under a hypothetical 0.01 oz exposure scenario. At unchanged historical returns its G7 exposure ceiling is about 0.023712 oz, whereas the current account minimum is 1 oz. That ceiling is a screening calculation, not a broker-qualified trade size or advice to change funding.

A concrete next attempt needs an accessible smaller-contract demo/practice account, verification of its actual symbol economics and margin, actual target-venue bid/ask costs and fee terms, and untouched subsequent validation data. The user has been asked whether an existing account is available; no replacement account or credential was assumed. No account was opened or funded.

S11’s 52-trial adjusted lower bound remains negative and it has only 26 trades in 2021–2025. The third round increases the cumulative research history to 68; S11’s preserved earlier results are not silently recalculated or relabeled as independent evidence. The old 52-trial adjustment cannot be treated as a complete adjustment for the expanded search.

## Verification and artifacts

184 Python tests passed; Ruff passed. New tests validate the probability calculation against exhaustive enumeration, boundary cases, a single large loss, decimal equality at the risk limit, and the refusal to infer approval from an inconclusive bound. Source snapshots, all 16 trade counts/means, original freezes, previous research manifests, and Step 7 artifact hashes were verified. The 2026 holdout was not reopened.

- [Registered protocol](protocol.json)
- [All new results](out/SUMMARY.json)
- [S11 loss-run calculation](out/S11_LOSS_RUN_BOUND.json)
- [Fresh account qualification](venue/QUALIFICATION.json)
- [Raw broker export](venue/broker_snapshot.csv)
- [Verification](out/VERIFICATION.json)
- [Previous S11 evaluation](../goldnix_round2/out/full_evaluation/RESULT.json)

Output creation is exclusive and refuses to overwrite this experiment. Any later work must preserve this record and use a separately registered protocol.
