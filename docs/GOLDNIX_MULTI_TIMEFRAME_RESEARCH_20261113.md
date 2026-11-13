# M1 / M5 / M15 / H1 / H4: implementation research

Research date: 2026-11-13. This note proposes implementation checks; it does not
register a trading strategy, change the running EA, or establish profitability.
The choice between one combined hierarchy and selectable entry profiles remains
open pending the user's clarification.

## Candidate hierarchy to evaluate

If the user chooses one combined analysis, a possible role assignment is:

| Timeframe | Proposed role |
|---|---|
| H4 | Broad market regime and major nearby price levels. |
| H1 | Directional bias: long, short or unresolved. |
| M15 | Setup and the price level that would invalidate it. |
| M5 | Confirmation that the setup is progressing. |
| M1 | Precise entry trigger after the required conditions exist. |

This is a research hypothesis, not an implemented or profitable method. A
potential conflict rule is to wait when higher-timeframe bias is unresolved;
lower-timeframe pullbacks need not have the same candle colour as H4. If the
user instead wants selectable entry periods, each profile needs its own
explicit mapping and exit rules; changing a chart tab cannot establish those
rules. M1 has no lower candle period within this requested set, and H4 has no
higher one. Do not claim to check both sides for every selectable profile.

The current minimum trade is 0.01 lot and its hard planned-loss limit is 5 USC
(USD0.05). Higher-timeframe volatility or structural stops may exceed that
budget even at minimum size. Reject an ineligible setup rather than shrinking
its invalidation stop or increasing cash risk merely to force a trade. The
one-time execution check's capped stop is a separate operational check, not a
template for qualifying this strategy. These constraints are visible in the
EA and policy files linked below.

## What the current implementation actually does

The active EA source explicitly requests `PERIOD_M1` in its warmup, current-bar
lookup and update loop. Its normal signal compares the completed M1 midpoint
close with the previous 20-bar channel. It does not consult M5, M15, H1 or H4 to
classify trend. See [GoldnixAutoM1.mq5](../goldnix_auto_m1/GoldnixAutoM1.mq5)
and [AutoM1Policy.mqh](../goldnix_auto_m1/AutoM1Policy.mqh).

Changing the displayed chart does not change an explicit `PERIOD_M1` request.
`PERIOD_CURRENT` instead refers to the attached chart's period. A chart-period
change also causes EA deinitialization/reinitialization, so persistent order
intent and risk accounting must survive it. [Timeframe constants](https://www.mql5.com/en/docs/constants/chartconstants/enum_timeframes),
[OnDeinit](https://www.mql5.com/en/docs/event_handlers/ondeinit).

## Requirements derived from the official APIs

1. **Read completed bars explicitly.** In positional `CopyRates`, shift zero
   is the forming bar. For a current decision, request from shift one and check
   the returned count. Copied physical storage starts with the oldest bar;
   logical indexing depends on the array's series setting. Specify that setting
   deliberately and assert timestamps. [CopyRates](https://www.mql5.com/en/docs/series/copyrates).
2. **Align to the decision time.** `MqlRates.time` is the period's opening time,
   not when its high/low/close became known. For these fixed intraday periods,
   nominal completion is `open + PeriodSeconds(tf)`. A replay at time `t` must
   select only bars completed by `t`, rather than today's shift-one bar.
   [MqlRates](https://www.mql5.com/en/docs/constants/structures/mqlrates),
   [PeriodSeconds](https://www.mql5.com/en/docs/common/periodseconds).
3. **Do not equate a successful lookup with a closed or fresh bar.** `iBarShift`
   locates the bar corresponding to a timestamp. With `exact=false`, a missing
   bar can fall back to an earlier one; with `exact=true`, missing history can
   produce `-1`. Neither mode proves the returned bar was complete at the
   historical decision. Inspect its timestamp, completion and age separately.
   [iBarShift](https://www.mql5.com/en/docs/series/ibarshift).
4. **Treat missing data as unavailable.** A `CopyRates` request can initiate
   downloading/building and return fewer rows than requested. Retry later;
   do not interpret incomplete warmup as neutral or bearish trend. Check each
   symbol/timeframe's synchronization independently through the boolean-return
   `SeriesInfoInteger` overload and `SERIES_SYNCHRONIZED`. These checks supplement
   the required row count. [CopyRates](https://www.mql5.com/en/docs/series/copyrates),
   [SeriesInfoInteger](https://www.mql5.com/en/docs/series/seriesinfointeger).
5. **Check indicator readiness separately.** If using indicator handles,
   `BarsCalculated` exposes calculated-buffer counts and can return `-1` when
   data are not calculated. A valid handle alone is insufficient; validate the
   buffer-copy count and finite, nonempty values too. Timeframe histories are
   prepared independently, even when another timeframe is ready.
   [BarsCalculated](https://www.mql5.com/en/docs/series/barscalculated),
   [Data access](https://www.mql5.com/en/docs/series/timeseries_access).
6. **Keep the time basis explicit.** `TimeCurrent` is server quote time; in a
   timer it may refer to another Market Watch symbol's latest quote. It is not
   proof that this symbol's quote is fresh. Implementation recommendation:
   retain per-symbol quote freshness and recorded broker bar boundaries; verify
   server-to-UTC conversion before comparing with UTC-aggregated research bars,
   especially H4. [TimeCurrent](https://www.mql5.com/en/docs/dateandtime/timecurrent).

Derived design rule: each decision should log its timestamp, each timeframe's
selected bar opening/completion timestamps, readiness, trend result and rejection
reason. Never forward-fill a missing higher-timeframe observation indefinitely.
At a boundary, confirm that the terminal has advanced the relevant series before
consuming its newly completed bar. Freeze all selected data to one decision time
so sequential reads cannot mix pre-boundary and post-boundary information.

## Verification cases proposed before any deployment

| Case | Required observation |
|---|---|
| H1 candle 10:00–11:00; decision 10:59 | Its final OHLC is unavailable. |
| Decision exactly 11:00 | Use 10:00 H1 only after the series confirms completion. |
| Change future H4 high/low/close | Earlier M1/M5 decisions remain identical. |
| History gap / weekend / delayed update | No silent stale-bar substitution or invented candle. |
| Only 99 of 100 requested bars returned | Explicit unavailable state; no entry. |
| Indicator handle exists but buffer is unready | No trend classification from empty values. |
| Switch displayed M1 to H4 | Explicit analysis periods stay fixed; no duplicate order or reset daily loss. |
| BUY and SELL mirrored fixtures | Equal timing and risk rules in both directions. |
| Independent replay versus native snapshot | Same selected bars, indicator values and decisions at boundaries. |

These are proposed behavioral checks, not tests executed by this research note.

## Existing evidence limits

The older [U01 study](../goldnix_mtf/README.md) already used H1 direction, M15
pullback and M5 break/retest/reclaim. It failed G1–G5, with only 788 trades; 36
software tests and 400 higher-timeframe availability comparisons passed. The
completed-bar selection seam in [method.py](../goldnix_mtf/method.py) is reusable
engineering evidence, not an endorsed signal rule.

All 12 subsequent U02–U13 retest/hold variants also failed profitability checks.
The separate [H01 replay](../goldnix_mtf2/README.md) passed the original numerical
Step 6 gates using H1 channel signals and M5 execution detail. Its selection-
adjusted bound remained negative; it does not validate this proposed five-
timeframe method, nor establish an M1 or frequent M5 strategy.

The hierarchy, trend definition, conflict rule, entry timeframe, stop placement,
target and holding-time policy must be frozen as a new research candidate before
performance evaluation. Reading five timeframes is technically feasible;
whether doing so improves results remains an empirical question.
