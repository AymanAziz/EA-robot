# M5 execution review and a separate signal-based successor

Reviewed 2026-11-12. The current M5 program, its installed binaries, parameters,
and running job were preserved. This review adds documentation and a frozen
copy of evidence; it does not change or deploy trading rules.

## Why every entry is BUY

The answer is in [DemoRoundTrip.mq5](../goldnix_venue/DemoRoundTrip.mq5), line 140:

```mql5
const bool sent=trade.Buy(0.01,DEMO_SYMBOL,0,sl,0,"Goldnix demo execution");
```

The direction is literal code. There is no SELL-entry branch, direction model,
trend detector, or indicator calculation before that call. The MT5 API defines
this method as opening a long position. A SELL deal used to close an existing
BUY in the history is not a new short entry.
[MetaQuotes CTrade.Buy documentation](https://www.mql5.com/en/docs/standardlibrary/tradeclasses/ctrade/ctradebuy).

[DemoSession.mq5](../goldnix_venue/DemoSession.mq5), lines 45–62, schedules attempts
from the session start in 300-second slots and calls this function. Selecting
M5 checks the chart period and sets the target holding time to five minutes;
it does not add analysis of five-minute candles. Slots are anchored to program
startup, not necessarily to a broker candle close.

The existing checks answer operational questions: is this the expected demo
account, is the quote fresh, is the lot size allowed, is margin available,
and are the account/clock/connection and loss limits acceptable? Those checks
do not answer whether the next market move is more likely up or down.

This was built and described as an execution test. It is useful as a repeatable
baseline and for testing orders, stops, timers, recovery, and receipts. It is
not an implemented version of the earlier H1 strategy research. Extending it
to M5 did not turn it into a directional strategy.

## Findings from the actual run

The review freezes **the first 13 completed trades**, through **12:50:28 UTC /
20:50:28 Malaysia time**. The session was still running when this snapshot was
taken; these are partial results, excluding later trades and any open-position
P&L. All 26 entry/exit deal records reconcile to the session audit. The separate
post-session broker-history verification has not yet happened for this snapshot.

| Measure | Observed value |
| --- | ---: |
| BUY entries / SELL entries | 13 / 0 |
| Gains / losses | 3 / 10 |
| Broker stop-loss exits / timed exits | 8 / 5 |
| Net result | −8.85 USC = −$0.0885 |
| Total winning P&L / total losing P&L magnitude | 3.76 / 12.61 USC |
| Profit factor, descriptive only | 0.298 |
| Mean net result per trade | −0.681 USC |
| Maximum realized drawdown within these trades | 11.25 USC |
| Quoted entry spread, gold price units | 0.38–0.44; median 0.41 |
| Median quoted spread / actual entry-to-initial-stop distance | 29.1% |

The stop distance is `max(1.0, broker minimum + 0.05)` below the current bid,
subject to an upper distance bound. With a BUY filled near ask, the initial
entry-to-stop distance includes the spread. The program does not scale this
distance with ATR or place a take-profit target; it uses the stop or the timer.
The existing spread ceiling is 2.00 gold price units, not a volatility- or
stop-relative filter. See lines 120–140 of the execution source.

The 29.1% number is a cost-to-initial-risk diagnostic, **not** a percentage of
account equity and **not** a fee to subtract again. Bid/ask execution already
embeds spread in the recorded P&L. The sum of entry spread equivalents is
5.30 USC at this contract's measured exposure; that is an entry-side diagnostic,
not a complete reconstruction of all round-trip costs.

This sample establishes that the current test repeatedly bought and lost money
over this interval. It does not establish a dependable downtrend signal, prove
that an H1 filter would have avoided those trades, or show that reversed trades
would earn +8.85 USC. A short position has different executable quotes and
stop-hit paths. Those counterfactuals need their own chronological simulation.

Evidence: [review JSON](../goldnix_venue/out/review_M5_20261112T114339Z_first13/REVIEW.json),
[trade table](../goldnix_venue/out/review_M5_20261112T114339Z_first13/trades.csv),
[copied source and audits](../goldnix_venue/out/review_M5_20261112T114339Z_first13/),
[hash manifest](../goldnix_venue/out/review_M5_20261112T114339Z_first13/MANIFEST.json).

## What to preserve and what to investigate separately

Keep this version as the fixed execution baseline. Keep its minimum demo size,
one-position restriction, expected-account checks, server-side stop, persistent
entry markers, interruption handling, bounded run, and receipt reconciliation.
Create a separately named research candidate if implementation is requested;
do not switch the running baseline's rules halfway through its measurement.

| Proposed responsibility | Question it answers | Initial research scope |
| --- | --- | --- |
| H1 context | Is there a defined upward, downward, or neutral regime? | One declared trend rule on completed H1 bars; neutral means SKIP |
| M15 setup | Is there an eligible pullback or continuation setup within that context? | A separate added condition whose benefit must be measured |
| M5 trigger | Has a specific completed-candle trigger occurred? | One declared trigger; enter on a subsequent executable quote |
| Cost and risk checks | Is this opportunity affordable at current spread and volatility? | Record spread relative to stop/ATR, monetary stop risk, and margin |
| Optional activity filter | Is quote activity unusually low or high? | Compare with and without a clearly defined tick-volume filter |

The key interface is **BUY / SELL / SKIP with a recorded reason**. A slower
trend should grant direction eligibility, not force an entry every five minutes.
H1 and M5 may disagree; skipping is a valid outcome. More timeframes and more
indicators are not independent votes that automatically increase confidence.

The detailed primary-source homework and one **unvalidated, fixed starting
hypothesis** are in [the multi-timeframe research note](GOLDNIX_MTF_SIGNAL_HOMEWORK_20261112.md).
The order of evaluation should first compare an M5 trigger alone with the same
trigger plus an H1 filter, then test the incremental M15 and volume conditions.
That makes it possible to tell which component helps, hurts, or simply removes
trades. Do not choose parameters by looking for a better result in today's run.

Adding a SELL output requires a separate side-aware execution adapter as well:
the existing calculations use `ORDER_TYPE_BUY`, a BUY adverse move, and a stop
below bid. SELL margin/profit calculations, ask-side stop triggering, closing
quotes, and fill accounting must be implemented and tested explicitly. Merely
renaming the signal or negating BUY profit is insufficient.

## Data and timing rules before testing a successor

1. Use only candles fully closed at the decision time. MT5 position zero is the
   current bar. At an M5 decision within an hour, the final value of that entire
   hour is unavailable; joining it from a later H1 export would leak future
   information. Record the actual source-bar timestamps for each decision.
   [MetaQuotes CopyRates](https://www.mql5.com/en/docs/series/copyrates).
2. Record both tick and trade-volume fields, including whether meaningful trade
   volume is supplied. The current exporter writes `tick_volume` only; it does
   not inspect `real_volume`. Therefore this review cannot claim the broker's
   trade volume is available, missing, or zero. The fields are distinct in
   [MetaQuotes MqlRates](https://www.mql5.com/en/docs/constants/structures/mqlrates).
3. Obtain enough same-broker H1/M15/M5 history and warm-up data. The current
   150-bar M5 export is about 12.5 hours, not sufficient warm-up for a long H1
   moving average. Current entry quotes and ten-second account heartbeats also
   cannot reconstruct every intratrade stop path or a complete spread history.
4. Prefer recorded broker ticks with bid/ask prices for execution replay; inspect
   missing periods rather than assuming every tick is real. MT5 can generate
   ticks where recorded tick data is missing, and generated spreads differ from
   tick-varying spreads. Include observed fees and measured slippage assumptions.
   [MetaTrader real and generated ticks](https://www.metatrader5.com/en/terminal/help/algotrading/tick_generation).
5. Freeze rules, costs, dates, warm-up and trial count before evaluating an
   untouched later period. Log every BUY, SELL and SKIP, including failed data
   checks. Compare identical risk/exit assumptions when isolating entry logic;
   investigate volatility-based stops separately from signal changes.

## Relationship to the earlier research

The repository already researched symmetric H1 trend/pullback and channel
families. That work is separate from the current timed demo runner. The explicit
registry reached **68 variants**; S11's earlier selection-adjusted bound was
negative and independent validation remained outstanding. The later Cent
account qualification resolved a contract-size/margin hurdle; it did not
approve the strategy. See the [signal-family note](GOLDNIX_SIGNAL_RESEARCH_20261112.md),
[first research round](../goldnix_research/README.md),
[S11 evaluation](../goldnix_round2/README.md), and
[third-round limitations](../goldnix_round3/README.md).

This review ran no strategy backtest, searched no indicator parameters, reopened
no historical holdout, and placed no extra orders. The prior trial registry and
Step 6 status are unchanged. A three-hour session can reveal operational issues
and supply observations; it cannot by itself validate a durable trading edge.
