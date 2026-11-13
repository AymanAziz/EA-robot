# Automatic M1 demo EA

Version **1.20** adds the requested profit protection. Its engineering validation
is recorded in `deployment/profit_protection_validation/`. Full Steps 1–8
qualification is reported separately in [qualification/REPORT.md](qualification/REPORT.md).

`GoldnixAutoM1` evaluates completed one-minute candles on `XAUUSD.c`. It is
attached to the saved Default chart profile, so opening MT5 starts capture
automatically. There are no user-defined operating hours. MT5, its connection
and the Mac must remain running; closing the lid can interrupt capture.

This is a separate M1 version of the existing M5 strategy: a breakout of the
previous 20 completed bars, midpoint ATR14, a 2 ATR stop (minimum 0.50), and a
3R target. BUY and SELL use the same rules in opposite directions. It preserves
0.01 lot, the $0.05 / 5 USC planned-risk cap, seven daily order attempts, the
10 USC daily equity-loss guard and the -2R realized entry halt. Broker-session,
Friday, holiday, spread, margin and fresh-quote checks still apply.

The chart shows the latest evaluated M1 candle, signal direction, planned risk,
decision reason, permissions and order attempts. An active EA can legitimately
have no trades when no signal passes its entry checks. Startup and reconnect
warm 100 completed bars, then wait for a fresh candle; missed entries are not
replayed. Native server SL/TP protect confirmed positions when MT5 is closed.

Version 1.10 adds an explicitly requested, one-time demo execution check.
`ExecutionCheckRequestUtc=0` disables it by default. A nonzero UTC request
expires after one hour and uses the next fresh completed M1 candle's midpoint
body to choose BUY/SELL (a doji skips entry). It still needs every existing
identity, spread, risk, margin, session and protection check. A flushed,
read-back receipt claims the request before the normal durable order intent;
restarting cannot repeat that request. A crash between claim and send can skip
the check. The check consumes the same daily budget as ordinary entries.
Only this execution check caps its ATR stop to a **4 USC planned risk**, leaving
1 USC headroom below the 5 USC hard risk limit. It never enlarges a smaller ATR
stop and rejects costs that leave less than the minimum stop distance. Ordinary
strategy entries retain the full 2 ATR / 0.50-floor stop and can be skipped when
that exceeds their risk cap. Neither cap guarantees a realized loss under gaps.

This check proves broker execution only. It is labelled
`requested_execution_check` in `signals.csv` and `entries.csv` and is kept
separate from strategy performance in reviews. Normal channel signals resume
after the claim. `entries.csv` records broker order/deal IDs, fill, direction,
volume and SL/TP; the magic ID joins confirmed entries to reconciled exits.

## Profit protection (P01)

The original entry-to-SL distance is fixed when the actual filled position is
first reconciled. After executable gross profit reaches **0.5 of that risk**,
and the cost-reserve threshold also fits, the EA attempts to retain **50% of
the highest executable gross profit observed by its one-second timer**. BUY uses
Bid; SELL uses Ask. This is a declared starting rule, not a fitted optimum.
Small profits below activation can still reverse into a loss.

The cost reserve includes twice the known entry commissions/fees, negative
accrued swap, and 0.20 USC extra. Unknown exit charges and slippage can exceed
this reserve. A profitable stop is not a guarantee of positive realized net
P/L. The same reserve is USD0.002 in the tester-only USD fixture; production
identity still requires the exact USC demo account.

SL only tightens and TP stays at its original value. The proposed stop is
rounded to the symbol tick grid and checked against stop/freeze restrictions.
An update must improve SL by at least max(one tick, 0.05 of original risk).
Requests are limited to one per two seconds. A successful API return alone
does not confirm protection: the broker return code and actual SL/TP readback
must agree. Rejected updates retain the last accepted server stop and retry.
If the recorded profit floor is breached, the EA requests an early full close
and persists that intent until closure is confirmed. There are no partial
closes, additional entry orders, MTF reversal predictions or structure exits.

Each owned position has a checksummed, read-back `protection_<magic>.csv`
journal in the existing shared risk root. It retains original entry/SL/TP,
observed peak, confirmed SL and close intent. An interrupted write after broker
acceptance can recover a tighter actual SL. Missing/corrupt protection records
or weakened protection fail closed. A missing record may only be initialized
while the observed stop is still adverse; it cannot invent original risk from
an already profitable stop. The shared 19-field daily risk checkpoint remains
unchanged, and the realized-R denominator still uses the original strategy
distance. The existing restart/disconnection recovery-close policy remains;
accepted server SL/TP stay in place when the terminal is unavailable.

The policy is [declared here](protection_protocol.json). The 30 shared planner
cases run both under native MQL5 and a C++ compatibility wrapper; they are the
same cases, not 60 independent tests. Native journal checks plus the original
38 regression cases make 78 native checks. The separate tester-only broker
fixture alternates entries and injects rejected requests; it is deliberately
not a strategy profitability or full trade-list parity test.

The M5 source and evidence remain in `../goldnix_auto_m5/`. Both variants share
the **existing** `MQL5/Files/GoldnixAutoM5Demo/` risk checkpoint, commissioning
marker, ownership lock and magic range. This legacy folder name is intentional:
switching timeframe must not restore a consumed daily budget or allow two
owners. M1 records use `runs/M1_AUTO_*/`, with `m1.csv`, `signals.csv`,
`events.csv`, `trades.csv` and 24-byte binary quote records. Only M1 is attached
after the handoff. Do not delete state to bypass a halt.

Read current status and independently verify native signal calculations:

```sh
PYTHONPATH=goldnix:. .venv/bin/python -m goldnix_auto_m1.ops status
PYTHONPATH=goldnix:. .venv/bin/python -m goldnix_auto_m1.ops verify-signals
PYTHONPATH=goldnix:. .venv/bin/python -m goldnix_auto_m1.review
```

`deployment/ONE_HOUR_REVIEW.json` identifies the requested observation start
and review time. It does not impose a stop time or schedule a chat reply.
The EA continues its automatic operation when MT5 is running. The review
command reads records across restarts and reports confirmed entries, closed
results, current exposure and skipped signals.

Deployment evidence is in `deployment/`. Compile and policy tests check M1
timing, BUY/SELL symmetry, duplicate/stale signal rejection, checkpoint parsing
and daily risk rules. Reopen and signal-parity checks validate operation in
MT5. This M1 variant remains an experimental DEMO and does not inherit any
Step 6/7/8 performance qualification from other timeframes.
