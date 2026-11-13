# Protecting floating profit while allowing continuation

Research date: 2026-11-13. Scope: the experimental `GoldnixAutoM1` DEMO EA.
This note proposes behavior and verification; it does not change running orders,
register performance results, or demonstrate an ability to predict reversals.

## What can be known before an exit

Completed price observations can identify a warning condition or invalidate a
previously declared setup. They cannot reveal whether the next move will be a
temporary pullback, a sustained reversal or a gap. Calling a warning a reliable
forecast would require independent evidence that this project does not have.

The practical objective is to limit the profit surrendered after favorable
movement while retaining enough room for continuation. Earlier exits can save
some profits and also cut trades that would later reach TP. This trade-off is a
research hypothesis to measure, not a claim established by the API documentation.

## Current code and an integration conflict

[GoldnixAutoM1.mq5](../goldnix_auto_m1/GoldnixAutoM1.mq5) sets a fixed initial
SL/TP. It contains no `PositionModify` profit-management path. Existing forced
closes cover risk, recovery and session conditions rather than price-structure
reversal detection.

Its `Reconcile()` currently rejects `OrderCalcProfit(entry, SL) >= 0`, raises
`position_protection_or_risk_invalid`, and calls `CloseOwned()`. Therefore moving
the SL to entry or into gross profit would conflict with the existing invariant.
That needs a deliberate change before integrating trailing/break-even logic;
simply adding a stop-modification call is insufficient.

Keep the strict initial-entry loss check separate from ongoing protection.
A proposed ongoing invariant should permit valid nonnegative stop P/L while
requiring the protective stop to exist, never loosen, and never expose more
planned loss than the initial accepted limit. Preserve the original risk unit
for performance accounting; a tightened SL must not redefine past R multiples.
These are implementation recommendations derived from the current source.

## Primary-source execution requirements

| Requirement | Implementation consequence |
|---|---|
| SL/TP are stored and executed by the broker; EA actions require the computer and connection. | Keep a confirmed server SL throughout management. A disconnected EA cannot react to a new warning. [MT5 execution](https://www.metatrader5.com/en/terminal/help/trading/performing_deals). |
| Built-in trailing runs in the terminal. The latest placed SL remains active if the terminal is off. | An EA-managed trailing rule has the same availability dependency for subsequent modifications; an accepted stop is protection at a price level, not a future price forecast. [MT5 trailing](https://www.metatrader5.com/en/terminal/help/trading/general_concept#trailing_stop). |
| Long protective levels use Bid; short protective levels use Ask. | Measure excursion, SL triggers and proposed exits on executable quote sides, not midpoint or chart color alone. [MQL5 spread/level rules](https://www.mql5.com/en/book/automation/symbols/symbols_spreads_levels). |
| Stop-distance and freeze restrictions can prevent modification near the current quote. | Read the current broker properties, validate price direction/distance and handle rejection without removing the existing SL. [MQL5 spread/level rules](https://www.mql5.com/en/book/automation/symbols/symbols_spreads_levels). |
| Price tick size and permitted volume min/step are symbol properties. | Round to the tick grid; decimal digits alone do not prove a valid price. With a 0.01-lot position and 0.01 minimum, half-close at 0.005 is ineligible. Recheck live specifications before any operation. [Symbol properties](https://www.mql5.com/en/docs/constants/environment_state/marketinfoconstants). |
| `PositionModify()` returning true only confirms its basic request checks. | Use the owned position ticket, check `ResultRetcode()`, then read back actual SL/TP. Do not label protection active merely because the local function returned true. Preserve the existing TP in the modification. [PositionModify](https://www.mql5.com/en/docs/standardlibrary/tradeclasses/ctrade/ctradepositionmodify). |
| `PositionClose()` also requires checking the server result. | A reversal-exit decision is not a confirmed exit. Reconcile the actual position/deal history before reporting realized profit. [PositionClose](https://www.mql5.com/en/docs/standardlibrary/tradeclasses/ctrade/ctradepositionclose). |
| `CTrade::PositionClosePartial()` is documented for hedging accounting. | Do not assume identical partial-close handling on netting and hedging accounts. Partial closing is unnecessary for this minimum-sized position. [PositionClosePartial](https://www.mql5.com/en/docs/standardlibrary/tradeclasses/ctrade/ctradepositionclosepartial). |

MT5 documents that stop execution can slip and that market-execution prices are
determined by the broker. Consequently, a stop beyond the entry does **not**
guarantee positive realized net P/L through gaps, spread changes, fees or execution
delay. A stop at entry is only price break-even; costs still need accounting.
[Execution modes and stops](https://www.metatrader5.com/en/terminal/help/trading/performing_deals).

`OrderCalcProfit` estimates a price-to-price result in account currency under
current conditions. Net-profit claims must also reconcile the position's
commissions, fees and financing, which the current completed-trade history loop
already records. [OrderCalcProfit](https://www.mql5.com/en/docs/trading/ordercalcprofit),
[current reconciliation source](../goldnix_auto_m1/GoldnixAutoM1.mq5).

## Candidate behavior to specify and test

The following is a proposed state model, not a tested trading rule. Numeric
thresholds, price structures and analysis periods must be declared before
evaluating results; do not tune them against a single recently observed trade.

1. **Hold:** initial server SL/TP remain. A single opposite-colored candle is
   insufficient to label the setup invalid. The chosen structural level must
   have been known before the decision; a swing requiring later bars becomes
   usable only when those bars have closed.
2. **Protect:** after a declared favorable-excursion threshold, propose a tighter
   SL using a declared structural or volatility distance. For BUY, raise the
   stop only; for SELL, lower it only. Retain room for the normal pullback defined
   by the policy. Never widen the stop again when price reverses.
3. **Exit on invalidation:** a completed-bar condition that breaks the declared
   setup can request an early exit. Confirmation is later than the first adverse
   tick, so the server SL must remain able to act intrabar. The initial TP stays
   active while the trade remains valid.
4. **Unavailable:** missing/stale analysis data must not fabricate trend or a
   reversal. Keep confirmed server protection and log the unavailable reason;
   existing risk/session emergency rules still take precedence.

For an M1 entry, using M5/M15 context is a distinct candidate from using only
M1 structure. The pending M1/M5/M15/H1/H4 design is not already active and has no
performance qualification. See [MTF research](GOLDNIX_MULTI_TIMEFRAME_RESEARCH_20261113.md).

## Verification before claiming improvement

Required behavioral cases:

- Mirrored BUY/SELL behavior using Bid/Ask correctly, including spread widening.
- Break-even and profitable stops survive reconciliation; initial risk still
  rejects invalid or excessive-loss entries.
- Stops never loosen, TP is preserved, and failed modifications do not erase
  protection or falsely advance the recorded protection state.
- Tick-size rounding, stop/freeze restrictions, stale quotes and changed broker
  settings produce explicit outcomes.
- Restart/chart change retains position identity, accepted stop and original
  risk accounting; no duplicate close request after confirmed closure.
- Future bars cannot change earlier structure levels or decisions. Test a
  normal pullback followed by TP, a reversal after profit, and an intrabar gap
  through the proposed stop before any confirmation can occur.
- The 0.01 minimum-sized position never produces an invalid partial close.

For performance evaluation, retain the existing fixed-SL/TP strategy as the
baseline. Compare the same entries first to isolate exit effects, then replay
the complete strategy because earlier exits affect later eligibility and daily
halts. Measure net expectancy, drawdown, profit surrendered from maximum favorable
excursion, and missed subsequent TP outcomes after early exits. Report uncertainty
and losing cases rather than only the number of saved trades. These metrics and
the two-stage comparison are proposed research design choices.

MT5 supports broker real-tick testing, execution-delay simulation and a separate
forward period to reduce historical fitting. These facilities support such a
comparison; they do not establish that this proposed reversal rule works.
[MT5 strategy testing](https://www.metatrader5.com/en/terminal/help/algotrading/testing).
This research note has not executed those tests or changed the EA.
