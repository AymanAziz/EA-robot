# D01 experimental demo — 2026-11-13

The user explicitly requested activation of the H4 → H1 → M15 → M5 method on
the existing demo account after seeing the failed H02/H03 results. This permits
an experimental demo deployment; it does not change any qualification result.

Step 6 remains FAIL/INCOMPLETE and Step 7 remains NOT RUN: no new untouched
holdout exists. Engineering tests cannot substitute for either gate.

D01 retains H4 EMA50 direction and three-bar slope (100 complete H4 bars
minimum), H1 midpoint channel20 and simple ATR14, frozen SL/TP, and M15 warning
followed by the next consecutive M5 failure confirmation. All bars are closed
and constructed from actual separate Bid/Ask ticks. A warning requires an
entire M15 interval after entry. Confirmation requests an exit at the next
available quote; it does not predict a reversal or guarantee its fill.

Two deliberate differences make this a NEW variant (at least variant 89):

- Candle boundaries follow the broker server clock displayed in MT5. The
  research used UTC boundaries. We do not guess a historical DST conversion.
- Existing P01 profit protection remains enabled: arm at 0.5 original risk,
  subject to costs; retain 50% of observed favorable excursion through a
  tightening SL and durable floor-exit intent. Original TP is unchanged.

Bootstrap uses the most recent 7,200 completed M5 bars, then catches up without
entering on old signals. EMA is seeded from the first 50 complete H4 bars in
that bootstrap. Consequently restart can cause a small seed difference; this
is recorded and is not represented as exact H03 parity.

The EA runs on the saved M1 chart. Entries are H1 setups, not an M1 strategy.
No forced test order, daily-budget reset, live-account enablement, or parameter
optimization is authorized by this implementation. Existing shared risk state,
single-owner lock, 0.01 lot, 5 USC trade-risk cap, −2R/10 USC daily limits,
seven daily attempts, broker-session and Friday guards remain in force.

Validation boundaries: closed-bar feature/exit decisions against independent
Python fixtures and behavior cases; native MQL compile and probe; demo account,
saved chart and durable risk state before/after handoff. These are operational
checks, not profitability evidence. Further performance qualification must
freeze this distinct variant and register genuinely untouched future data.
