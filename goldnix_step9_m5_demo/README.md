# Daily M5 channel demo

**Replaced on November 13, 2026:** the user removed fixed operating hours.
This scheduler is disabled and unloaded. The new [persistent MT5 EA](../goldnix_auto_m5/README.md)
starts capture when MT5 opens; this timed implementation and its reports remain
available for review.

User-authorized experimental DEMO variant `M05_CHANNEL_SESSION_DEMO`, replacing
the scheduled H1 demo on November 13, 2026. It runs **00:00–06:30 every day,
Asia/Kuala_Lumpur**. The first M5 session starts partway through that window.
The H1 session was stopped, reconciled flat with zero trades, and its daily
LaunchAgent removed. See [handoff](HANDOFF.json).

Signals use completed **five-minute bars**: the prior 20-bar channel, simple
ATR14 on bid/ask midpoint OHLC, a 2 ATR stop with a 0.50 floor and 3R target.
BUY and SELL are symmetric. The native script warms 100 completed M5 bars
from broker tick history and first evaluates for entry on the next new bar.
M5 is the signal timeframe, not a five-minute holding-time limit. This version
does not add a higher-timeframe trend filter or volume confirmation.

The lot remains **0.01 lot / 0.01 oz**, with a **$0.05 / 5 USC planned-risk cap**,
one position, at most seven entry attempts per session, a -2R realized daily
entry halt, and a 10 USC session equity-loss guard. Native server SL/TP and
pre-order and post-fill risk checks remain. These limits can reject every
signal; fills, gaps and execution costs can exceed a planned loss estimate.

The broker's current symbol session ends at **05:58 Malaysia time**. The script
flattens its own positions at **05:56**, two minutes before that break, and
continues recording until 06:30. Actual broker session hours are read each run;
the existing Friday 20:00 UTC flatten takes precedence when earlier.

This M5 variant has **no inherited Step 6, 7 or 8 performance qualification**.
Native compilation, signal parity and operational checks establish that the
implementation runs as specified; they do not establish profitability.
Original H1 research and implementation are retained separately.

The LaunchAgent `local.goldnix.m05.daily-demo` runs independently of the chat.
The Mac must remain powered, logged in, awake, lid open and connected to MT5.
The controller prevents idle sleep while active. Account/server/currency
checks restrict execution to the expected JustMarkets Cent DEMO. A shared
terminal lock, session marker, source/binary hashes, close-only recovery and
persistent pending/blocked records prevent concurrent or repeated entry runs.

Each session writes `out/YYYY-MM-DD/`: `STATUS.json`, M5 input bars, decisions,
trades, raw bid/ask ticks, deployed source snapshots, and eventually a broker-
reconciled `RECEIPT.json` and `SUMMARY.md`. Daily review is from those records.

Read status without interrupting trading:

```sh
PYTHONPATH=goldnix:. .venv/bin/python -m goldnix_step9_m5_demo.runner status
```

Stop the current session while retaining tomorrow's schedule:

```sh
PYTHONPATH=goldnix:. .venv/bin/python -m goldnix_step9_m5_demo.runner stop
```

Stop and disable future sessions:

```sh
PYTHONPATH=goldnix:. .venv/bin/python -m goldnix_step9_m5_demo.runner disable
```

`runner check` restarts MT5 for deployment preflight; use `status` for routine
inspection. After installation, changing deployed Python/MQL source requires
deliberate redeployment. See [operational sources](../docs/GOLDNIX_SESSION_DEMO_OPERATIONS_20261113.md).
