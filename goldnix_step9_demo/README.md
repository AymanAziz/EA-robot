# Daily H01 session demo

**Schedule replaced on November 13, 2026:** the H1 run was stopped and
reconciled flat with zero trades. Its LaunchAgent was removed. The active
daily demo now uses [M5 signals](../goldnix_step9_m5_demo/README.md); this H1
implementation and its reports are retained unchanged.

User-authorized experimental DEMO sessions: **00:00–06:30 every day in
Asia/Kuala_Lumpur**, starting with the remaining part of November 13, 2026.
This is a session-limited variant, `H01_SESSION_DEMO`. The original H01
Step 6/8 research is preserved; missing Step 7 qualification is not relabelled
as passed.

The native account check confirms `XAUUSD.c` currently closes its trading
session at **05:58 Malaysia time**. The script flattens its own positions
**120 seconds earlier, at 05:56**, then continues recording until 06:30.
H01's original Friday 20:00 UTC exit takes precedence when earlier. Broker
session hours are read from the actual symbol on each run, not assumed from
a general schedule. If the broker is unavailable, closure may be delayed;
unresolved reconciliation blocks further sessions.

The script retains the prior-20-bar H1 channel, simple ATR14 on separately
aggregated bid/ask OHLC, 2 ATR stop with a 0.50 floor, 3R target and $0.05
signal-close planned-risk filter at 0.01 lot / 0.01 oz. Both directions are
enabled. It also checks actual planned risk with `OrderCalcProfit` in USC,
refuses insufficient margin or broker-invalid stop distances, and closes a
fill whose confirmed SL risk exceeds 5 USC. These are additional execution
guards, not evidence that realized losses cannot exceed a stop estimate.

Session controls include one position, at most seven entry attempts, the
original -2R realized daily halt, a 10 USC session equity-loss guard, native
server SL/TP, an explicit UTC deadline, a 120-second broker-close buffer,
and a stop file. The controller and native script both enforce the boundary.
The native script checks the expected account, exact demo server and USC
currency. It rejects real accounts and the Strategy Tester. Closure targets
only tickets and pending orders owned by that session's magic range.

The implementation is a resident MQL script with a short polling loop. It
warms 100 completed H1 bars from real bid/ask tick history, evaluates only on
the next new H1 bar, and never enters retrospectively on startup. Missing
history, account/clock changes, connection loss or a suspended host stop new
entries. A repeated session marker prevents restarting entries after a
crash; recovery is close-only. Persistent pending/blocked records prevent an
unresolved session from being silently replaced by the next day.

The Mac LaunchAgent `local.goldnix.h01.daily-demo` starts the controller at
midnight and on login. A runtime Malaysia-time guard rejects launches outside
the session, except required close-only recovery. It runs independently of
the chat/model. `caffeinate` prevents idle sleep while the worker is active;
the Mac must remain powered, logged in, lid open and connected. A powered-off
or closed laptop is not an unattended trading host. Weekend sessions can
finish with no trades. The current risk cap can also legitimately produce
zero trades on open-market days.

Each date gets `out/YYYY-MM-DD/`: status, source snapshot, native H1 inputs,
signal decisions, broker deals, realized P&L, and captured session bid/ask
ticks for subsequent comparison. After cutoff, the controller reconciles
broker history, verifies the account flat with trading disabled, compares
native signal calculations with Python, and writes `SUMMARY.md` and
`RECEIPT.json`. This is local reporting; no external messages or automated
chat reviews are sent. We can review these files together each day.

Read status without interrupting the run:

```sh
PYTHONPATH=goldnix:. .venv/bin/python -m goldnix_step9_demo.runner status
```

Stop only the current session, keeping tomorrow's schedule:

```sh
PYTHONPATH=goldnix:. .venv/bin/python -m goldnix_step9_demo.runner stop
```

Stop the current session and disable future sessions:

```sh
PYTHONPATH=goldnix:. .venv/bin/python -m goldnix_step9_demo.runner disable
```

`runner check` is a deployment preflight that restarts the terminal; it is
not the daily review command and refuses to run while the controller owns
the session lock. Deployed source and native binary hashes are checked
before every session, so edits require deliberate redeployment.

Validation includes native compilation with zero warnings, a read-only
account/history/signal check, and tests for timezone boundaries, Friday and
broker cutoffs, ownership, partial exits and P&L reconciliation. The preflight
found that this terminal's `ScriptParameters` parser reads datetime strings
as leading integers; presets now use UTC epoch seconds, with a regression
test. Invalid deadlines were rejected before any order path was enabled.

See [operations sources](../docs/GOLDNIX_SESSION_DEMO_OPERATIONS_20261113.md).
