# Automatic MT5 capture and M5 demo EA

As of 13 November 2026, the active chart uses the separately preserved
[M1 version](../goldnix_auto_m1/README.md), at the user's request. This M5 source,
binary and deployment evidence remain unchanged. Both versions share the same
risk checkpoint and ownership lock; only M1 is attached to the active profile.
The M5 setup described below is retained as its historical deployment record.

Opening MT5 normally restores **GoldnixAutoM5** on the saved `XAUUSD.c` chart.
There is **no fixed starting hour or 06:30 cutoff**. Capture and analysis run
while MT5 is open, the Mac is awake, and the connection is available. M5 remains
the signal candle interval. The chart displays capture, warmup, market closure,
trading permission and risk-halt status.

This replaces the former daily LaunchAgent. Both previous H1/M5 schedules have
been disabled and unloaded. Their code, tests and session reports are preserved.
The EA is saved in the current `Default` profile; keep its gold chart attached
when closing MT5. No chat session, command-line launcher or app-wrapper change
is needed on subsequent opens.

The existing experimental demo strategy is retained: a breakout of the prior
20 completed M5 bars, simple midpoint ATR14, a 2 ATR stop with a 0.50 floor,
and a 3R target. BUY and SELL use symmetric rules. It retains **0.01 lot / 0.01 oz**,
the **$0.05 / 5 USC planned-risk cap**, a -2R realized entry halt and native
server SL/TP. With the session clock removed, the **seven entry attempts and
10 USC equity-loss guard apply per Malaysia risk day**. A new day's budget
starts once the previous owned position/intent is fully reconciled and flat.
Reopening MT5 does not reset an existing day's budget or its last signal.

Only the explicitly configured JustMarkets Cent DEMO identity, server, currency
and contract may trade. Turning off MT5's Algo Trading button leaves capture
and analysis running. An eligible signal still needs valid spread, margin,
fresh quote, market-session and risk checks. Broker close buffers, Friday and
holiday controls remain; they affect orders, not the capture operating hours.

After launch, reconnection, sleep or a data gap, the EA warms 100 completed bars
and waits for a new five-minute bar. It does not replay missed signals as trades.
Any previously owned position is reconciled and closed when permissions and the
broker allow before accepting fresh entries. An ambiguous order, damaged state
or inconsistent broker history blocks new entries for review. Account changes
cannot redirect orders to a different account.

Closing MT5 stops local capture and management. Existing server SL/TP remain;
app shutdown is not a guaranteed market exit. Actual fills, gaps and fees can
exceed a planned loss estimate.

State and records live in MT5's **terminal data folder**:
`MQL5/Files/GoldnixAutoM5Demo/`. The Mac wrapper and CLI use different Wine user
directories, so `FILE_COMMON` was deliberately replaced after a native reopen
test exposed separate state files. Both launch routes now share the same
checkpoint, ownership lock and logs. A checksum, schema, read-back confirmation
and commissioning marker reject missing/corrupt state instead of silently
resetting risk. The checkpoint is written before an order request. An exclusive
file handle prevents a second EA chart from acting concurrently.

`status.csv` is the latest heartbeat. `runs/AUTO_*/` contains events, completed
bid/ask M5 bars, signal decisions, reconciled closed trades and raw captured
quotes. Each binary quote is little-endian `int64 server_time_msc`, `float64 bid`,
`float64 ask` (24 bytes). An occurrence cursor preserves distinct ticks sharing
one millisecond. Reconnect gaps and fresh warmups are recorded explicitly.

Read status or compare the current run's native signals against Python:

```sh
PYTHONPATH=goldnix:. .venv/bin/python -m goldnix_auto_m5.ops status
PYTHONPATH=goldnix:. .venv/bin/python -m goldnix_auto_m5.ops verify-signals
```

Deployment checks cover native compilation, 22 native policy assertions,
captured-quote integrity, independent signal parity, exclusive locking and
ordinary app close/reopen with the same persisted risk counters and watermark.
Deployment commands that restart MT5 are for setup, not routine status checking.

This is a separately identified **experimental demo**, with no inherited
Step 6/7/8 performance qualification. Operational tests do not establish
profitability. See [native lifecycle research](../docs/GOLDNIX_AUTOSTART_EA_RESEARCH_20261113.md)
and [deployment evidence](deployment/).
