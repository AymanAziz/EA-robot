# Continuing Step 6 without confusing a numerical pass with validation

Research checked **2026-11-12**. Scope: read existing results, account
qualification and primary methods documentation. No strategy runs, parameter
searches, MT5 changes, orders, or external communications were performed for
this note. The user has authorized further research; no outcome is guaranteed.

## Three distinct claims must remain visible

1. **Raw G1–G9 result:** the existing numerical function applied to a named,
   frozen strategy, historical fill model, data and exposure.
2. **Confidence after selection:** whether apparent performance survives the
   search across unsuccessful as well as successful candidates.
3. **Venue evidence:** whether sizing, costs, margin and execution assumptions
   are supported for the actual broker/account and relevant dates.

These are separate reporting fields, not an opportunity to rename or weaken
the [original gates](../goldnix/gates/rules.yaml). A raw pass can be reported
accurately while the second and third claims remain unresolved. Extra
diagnostics must not silently become replacement G1–G9 thresholds.

## What the existing results actually establish

| Evidence | Saved conclusion |
|---|---|
| S11, unchanged 0.01 oz historical scenario | All nine raw numerical gates pass; 1,025 trades; mean `+0.120185R`; paired-bootstrap G1 lower bound `+0.038543R`; conditional annual p99 drawdown `$1.0121295`. |
| S11 selection evidence | Its **52-trial screening** lower bound is `−0.046556R`; only 26 trades occurred in era D, 2021–2025. This is distinct from the paired-bootstrap raw G1 result. |
| U01 H1→M15→M5 retest candidate | G1–G5 fail, G6–G9 pass; 788 trades; mean `−0.408820R`; no positive era. The gate function reports `INSUFFICIENT_DATA`, but profitability and edge fail independently of the count. |
| U01 search diagnostic | Cumulative explicit registry: 69 variants; selection lower bound `−0.547522R`. |

Sources: [S11 full result](../goldnix_round2/out/full_evaluation/RESULT.json),
[S11 screen and era counts](../goldnix_round2/out/S11/metrics.json),
[U01 final result](../goldnix_mtf/out/U01_final_review/RESULT.json).

S11 is an H1 channel strategy, not the user's H1→M15→M5 retest method. Its
numerical success cannot be relabelled as a successful U01 improvement.
Reducing exposure changes monetary risk under the same path; it cannot turn
U01's negative dimensionless expectancy or insufficient trade count into a
pass.

## What verified cent-account economics can legitimately update

The dated native qualification confirms JustMarkets-Demo6 `XAUUSD.c`, a
0.01-lot minimum representing **0.01 oz**, and `$0.01` loss per `$1` adverse
gold-price move at that volume, in either direction. At the captured quote,
minimum-order margin was `$0.0132`; the study budget was `$20`. The existing
qualifier already links this to S11's conditional `$1.0121295` p99 versus the
unchanged `$2.40` limit, while retaining `step6_approved:false`.
[Qualification](../goldnix_venue/out/justmarkets_cent_verified_20261112T080825Z/QUALIFICATION.json),
[native verification](../goldnix_venue/out/justmarkets_cent_verified_20261112T080825Z/VERIFICATION.json).

A new, dated evidence bridge can therefore say:

> S11 passes the unchanged raw G1–G9 historical model at an exposure now
> demonstrated by the cent demo; independent edge confirmation and historical
> target-venue cost/execution validation remain pending.

Preserve the old result's `account_verified:false` and 1 oz account comparison
as records of what was known then. Reference their hashes and the later
qualification instead of rewriting them. Linear monetary scaling is
conditional on identical trades, fills and proportional costs; minimum fees,
margin restrictions or changed eligibility can invalidate simple scaling.

The qualification is a snapshot, not evidence of all historical conditions or
the current free margin indefinitely. MetaQuotes specifies that `OrderCalcProfit`
and `OrderCalcMargin` use the current account/market context and return account
currency; margin calculation also excludes existing positions and orders.
[Profit calculation](https://www.mql5.com/en/docs/trading/ordercalcprofit),
[margin calculation](https://www.mql5.com/en/docs/trading/ordercalcmargin).

It cannot validate 2005–2025 JustMarkets spreads, commission, financing,
slippage or fill availability. Recent zero-fee demo deals do not license
removing unknown historical costs. Keep USC-to-USD conversion explicit and
the fixed study budget unchanged.

## Why continued selection needs its own evidence

White's Reality Check addresses the best model encountered across a
specification search relative to a benchmark. Sullivan, Timmermann and White
apply that approach to the full technical-rule universe. The relevant
inference concerns the search, not merely a confidence interval around the
eventual winner.
[White, original publisher abstract](https://onlinelibrary.wiley.com/doi/10.1111/1468-0262.00152),
[technical-rule application](https://onlinelibrary.wiley.com/doi/10.1111/0022-1082.00163).

Bailey and López de Prado show why selecting among more trials can inflate
reported Sharpe ratios. Their Deflated Sharpe Ratio uses trial information,
sample size and non-normality, including the issue of dependent trials. This
does **not** make DSR a drop-in name for our mean-R bootstrap or establish a
numerical probability that S11 is profitable.
[Author manuscript, §§ selection bias/DSR and Appendix 3](https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf).

Our local selection diagnostic uses the bootstrap percentile `0.05 / N`.
At `N=69`, 10,000 replicates provide only about **7.25 expected replicates**
below that quantile. This extreme tail is numerically sparse; it is not a
precise search-adjusted confidence certificate. The registry also omits some
earlier informal design decisions. Correlated variants do not justify erasing
trials or choosing a favorable effective count after seeing results.
[Screen implementation](../goldnix_research/screen.py),
[U01 diagnostic implementation](../goldnix_mtf/evaluate.py).

Keep the original 52-trial result as historical evidence, and report subsequent
69-plus-trial analysis separately. Any future search-aware method needs its
assumptions, candidate universe, common calendar/benchmark and computational
precision declared first. It supplements the frozen gates. More bootstrap
draws improve numerical precision, not the amount of independent market data.

## A defensible next research stage

Register a finite, mechanism-driven batch before evaluating it: exact variants,
shared costs/risk, chronology, selection rule, cumulative trial count and stop
condition. Retain all failures. Distinguish correctness fixes from strategy
changes: fixes need preserved old artifacts and an explicit correction record;
new parameters need new candidate IDs. Do not select random seeds, eras,
spreads or fill rules because they produce a pass.

The 2005–2025 history is already examined. A chronological replay or walk-forward
analysis remains useful for stability and leakage checks, but cannot become
untouched validation merely by repartitioning familiar dates. The consumed
2026 holdout stays consumed. A final frozen candidate needs genuinely unseen
future observations for independent confirmation; a new data vendor over
familiar dates addresses feed sensitivity rather than restoring independence.

For later broker execution validation, real ticks preserve changing intraminute
spreads better than generated ticks. MT5 can generate replacement ticks where
minute bars lack tick history, so inspect coverage and logs. Bid/ask execution
still differs from chart prices.
[MetaQuotes tick documentation](https://www.metatrader5.com/en/terminal/help/algotrading/tick_generation).

Record actual commission/margin settings and declared execution-delay
assumptions; MT5 exposes these separately. Its rough profit-in-pips mode omits
commission, swap and margin control, making it unsuitable for an account-risk
claim.
[MetaQuotes tester settings](https://www.metatrader5.com/en/terminal/help/algotrading/testing).

U01's successful native indicator/timeframe parity validates that limited
implementation boundary. It does not validate historical spreads, tick-level
fills or strategy profitability.
[Recorded parity scope](../goldnix_mtf/parity/out/MTF_PARITY_20261112T134656Z/RESULT.json).
