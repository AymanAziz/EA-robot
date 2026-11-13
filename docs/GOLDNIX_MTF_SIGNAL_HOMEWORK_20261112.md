# GOLDNIX: higher-timeframe signal homework

Researched **2026-11-12**. This note proposes a separate research candidate.
It does not modify the running demo, native scripts, presets, account, or any
frozen research result. No new strategy was backtested or traded for this note.

Follow-up: the user requested analysis of false breakouts **before any new
strategy test**. Read the [false-breakout analysis](GOLDNIX_FALSE_BREAKOUT_ANALYSIS_20261112.md)
before treating the candidate below as a test specification. Its previous-bar
M5 crossing rule remains an unvalidated idea; causal level definitions,
confirmation rules and data requirements are still to be settled.

## Finding

The user's observation is correct. The current executor calls `trade.Buy`;
`DemoSession.mq5` schedules attempts and sets a five-minute holding target.
It has no SELL entry branch, trend classifier, indicator signal, or
volume-based entry decision. Selecting an M5 chart does not supply those rules.
The current version remains useful as an execution baseline.
[Executor](../goldnix_venue/DemoRoundTrip.mq5),
[session](../goldnix_venue/DemoSession.mq5).

The proposed improvement is a separate decision layer that emits **BUY, SELL,
or SKIP**, with the reason and input timestamps recorded. Higher-timeframe
direction, a lower-timeframe setup, and an entry trigger are testable ideas;
their combination is not automatically an advantage.

## What the evidence supports

| Evidence | Relevant finding | Limit on transfer |
|---|---|---|
| Moskowitz, Ooi and Pedersen (2012), original dataset | Time-series momentum across 58 futures/forwards, with a 12-month lookback and one-month holding period. | This does not validate H1/M15/M5 gold CFD entries or five-minute exits. [Authors' dataset](https://www.aqr.com/Insights/Datasets/Time-Series-Momentum-Original-Paper-Data). |
| Batten et al. (2018), intraday precious metals | Conventional moving-average parameters lacked predictive power; some searched combinations performed better for gold. | Searching parameters is part of the selection problem; their result does not establish our proposed EMA settings. [Author university record](https://research.monash.edu/en/publications/does-intraday-technical-trading-have-predictive-power-in-precious/). |
| Jin (2022), five-minute Chinese gold futures | Attractive technical-rule results did not reliably persist after costs, data-snooping controls and out-of-sample checks. | Different venue and sample; it challenges confidence in simple intraday rules without proving every rule fails. [Publisher abstract](https://www.sciencedirect.com/science/article/abs/pii/S1042443121001876). |
| Bailey et al. (2015) | Selecting from many backtests creates false discoveries; ordinary holdout practice can be unreliable in that setting. | A new filter and a favorable chart are not independent confirmation. [Original paper](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf). |

These sources motivate a controlled experiment, not a forecast that the
proposed strategy will make money. The existing project already studied
trend/pullback and channel families. Its explicit strategy registry remains
**68 variants**, and **Step 6 remains unapproved**. Reused history cannot become
untouched evidence by changing the timeframe.
[Earlier homework](GOLDNIX_SIGNAL_RESEARCH_20261112.md),
[first research round](../goldnix_research/README.md),
[third round](../goldnix_round3/README.md).

## Closed bars are essential

MetaQuotes documents position zero as the current bar, and distinguishes
logical series indexing from physical array order. Consequently, a live rule
should evaluate completed bars only, explicitly set/check array orientation,
and reject incomplete history.
[CopyRates](https://www.mql5.com/en/docs/series/copyrates).

For each historical M5 decision time, select the last H1 and M15 bars whose
closing times were already reached. At 10:35, an H1 bar opened at 10:00 is
still unavailable as a completed H1 signal. Do not backfill its eventual 11:00
close into earlier decisions. `iBarShift` locates bars by time and can return a
nearest bar across gaps; validate the resulting bar's timestamp and completeness.
[iBarShift](https://www.mql5.com/en/docs/series/ibarshift).

## One concrete candidate to test separately

**Unvalidated starting hypothesis; the numbers below are design choices, not
optimized settings or recommendations derived from the papers.** Evaluate once
after each M5 close. Use bid bars consistently for signals, and actual bid/ask
prices for execution. Seed EMA with the first N-close SMA, then apply
`alpha=2/(N+1)` recursively; discard the first 500 bars of each series.

| Layer | BUY condition | SELL condition |
|---|---|---|
| H1 direction | Last closed close > EMA50, and EMA50 > its value three closed H1 bars earlier | Both inequalities reversed |
| M15 pullback setup | Last closed low ≤ its EMA20 and close > EMA20 | Last closed high ≥ its EMA20 and close < EMA20 |
| M5 trigger | Last closed close > the preceding M5 bar's high | Last closed close < the preceding M5 bar's low |

All layers must agree; equality in a strict condition, missing history, stale
quotes, or disagreement means **SKIP**. A setup becomes available when its M15
bar closes. Only later M5 closes before the next M15 close may trigger it;
expire it at that next close. Allow one entry per M15 setup and one open
position. Example: a 10:15 setup can trigger at 10:20 or 10:25, not using the
10:15 candle retrospectively. H4 can be recorded as context without becoming
another filter in this first comparison.

For the first signal comparison retain the current demo size, five-minute
target exit, stop-distance rule, spread ceiling and loss controls. Mirror the
SELL execution correctly: enter at bid, exit at ask, with its stop above ask.
Do not negate BUY profits to simulate SELL: different spread sides and stop
paths change outcomes. ATR/structure stops, profit targets, news filters and
longer holding periods deserve separate experiments, so their effects are not
confounded with direction selection.

## Volume: useful input, provenance first

MT5 distinguishes `tick_volume` from `real_volume` (trade volume). Its Forex
volume documentation defines tick volume using price-change ticks. Thus the
available broker tick series is an activity proxy, not a direct measurement of
gold ounces bought or sold.
[MqlRates](https://www.mql5.com/en/docs/constants/structures/mqlrates),
[MT5 volume documentation](https://www.metatrader5.com/en/terminal/help/indicators/volume_indicators).

LBMA describes OTC precious-metal trading as bilateral. CME supplies exchange
gold futures and their own volume/market information. **Inference:** neither a
single broker's quote updates nor one futures contract's volume measures every
gold transaction worldwide. Futures inputs would also need synchronized
timestamps, contract-roll handling, and separation from the CFD execution feed.
[LBMA OTC guide](https://www.lbma.org.uk/publications/the-otc-guide/introduction),
[CME gold](https://www.cmegroup.com/markets/metals/precious/gold.html).

The present export records tick volume, not real volume, so usable
`XAUUSD.c` trade volume has not been established. Start with price rules; log
volume availability explicitly. An optional, separately counted candidate can
require the signal M5 bar's tick volume to exceed **1.2 times the median of the
preceding 20 completed M5 bars**, excluding the signal bar. This threshold is
also unvalidated. Never interpret missing trade volume as zero activity, or
claim high tick volume identifies buying pressure by itself.

## Fair test design

Keep the current run unchanged and freeze these comparisons before inspecting
their results. Proposed six configurations, **not yet registered or run**:

1. Existing scheduled BUY control.
2. Scheduled SELL control, simulated on the same opportunities.
3. Symmetric M5 trigger alone: BUY/SELL/SKIP.
4. H1 direction plus M5 trigger.
5. H1 direction plus M15 setup plus M5 trigger.
6. Configuration 5 plus the single declared volume gate.

Use identical execution/risk assumptions and data-quality exclusions. Freeze a
common decision clock and cooldown for comparisons claiming a filter's
incremental benefit: configuration 4 isolates adding H1 direction to 3, and 5
then isolates adding the M15 setup. Keep the current scheduled run as a separate
operational benchmark, rather than attributing timing differences to a filter.
Report matched decision opportunities, exposure, eligible opportunities, skipped
signals, trade counts, and both directions' outcomes so timing or fewer trades
cannot masquerade as directional skill.

Use chronological development, validation and untouched final blocks, with
forward-only walk-forward folds. Keep boundary-crossing trades out of training
labels; earlier data may warm indicators. Freeze every parameter, comparison,
fee assumption and success criterion before the final block. Record all tried
variants and failures. This is a protocol proposal, not a claim that a split
or walk-forward procedure eliminates selection bias.

Use target-venue bid/ask ticks where available, including variable spread,
commissions, slippage and financing when applicable. MT5 documents that real
ticks permit intraminute spread variation and that trades execute on bid/ask;
generated ticks can fill gaps in nominal real-tick tests, so audit coverage.
[MT5 tester mechanics](https://www.metatrader5.com/en/terminal/help/algotrading/tick_generation).

Report net expectancy and uncertainty, drawdown, payoff ratio, cost sensitivity,
regime/session stability and long/short results—not only win rate. Use blocks
that retain temporal dependence. A three-hour demo run is execution evidence;
it is too narrow to establish robustness across market conditions. The next
implementation should first log proposed decisions without placing additional
orders, leaving this execution baseline available for comparison.

## Access and preservation notes

MetaQuotes, LBMA, AQR, Monash, CME's gold page and Bailey's paper were opened.
Jin's publisher abstract was available in the indexed first-party result;
direct fetch returned HTTP 403, so no full-text methodological claims are made.
Southampton's duplicate record and CME's market-profile PDF also returned 403
and are not needed for the conclusions. No broker or terminal state was changed.
