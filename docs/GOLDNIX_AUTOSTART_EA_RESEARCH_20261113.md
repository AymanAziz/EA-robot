# GOLDNIX: native EA autostart and restart safety

Checked **13 November 2026** against primary MetaQuotes documentation. Scope: deployment and recovery engineering for capture/analysis whenever the user opens MT5, without fixed operating hours. The parent task is resolving whether automatic DEMO trading also continues. This note does not infer that answer, change strategy rules, establish formal qualification, or modify any terminal, configuration, code, or frozen research artifact.

## Recommended native deployment

**Attach a separate EA once to a normal XAUUSD.c chart in a saved profile, then reopen MT5 normally.** MetaQuotes explicitly states that EAs remain attached between terminal sessions and restore with their chart/settings. Scripts do not restore after terminal restart; the former resident `OnStart` script therefore does not satisfy this requirement by itself. Closing the chart unloads its programs. All these programs require the terminal to be running. [MQL program lifecycle](https://www.mql5.com/en/book/applications/runtime)

Profiles save open charts and their templates, including attached EAs. Changes to open charts are automatically saved in the current profile. A template includes the EA and its input parameters. Recommended installation: keep one designated normal chart, attach the EA with verified inputs, save a named profile and a named backup template, and leave that profile active. Avoid putting this EA in `default.tpl`, which applies to every newly created chart and invites duplicate instances. Switching profiles can disable automated trading depending on terminal settings. [Templates and profiles](https://www.metatrader5.com/en/terminal/help/charts_advanced/templates_profiles)

This is a native persistence mechanism, not a request to edit undocumented `.chr` internals or modify the macOS app wrapper. A regular close/reopen check in the actual Wine installation remains necessary; documentation alone does not establish that its current profile contains a working attachment.

## Startup config and template pitfalls

The documented `[StartUp]` alternatives are materially different:

| Configuration | Documented result | Deployment implication |
| --- | --- | --- |
| `Expert=...` with `Symbol=XAUUSD.c` | Adds a chart whose information is not saved; it does not reopen next time without the config. | Treat as temporary bootstrap/testing only. |
| `Expert=...`, `Symbol` omitted | Runs the EA on the first chart of the current profile; starts nothing if that profile has no charts. | Can attach to an existing persistent chart, but verify that chart and profile first. |
| `ExpertParameters=...` | Reads the parameter file from `MQL5\Presets`; omission uses defaults. | Do not silently rely on unspecified defaults. |

These are explicit platform rules. Combining attachment to an existing profile chart with profile persistence is a defensible deployment inference; verify the resulting attachment by reopening without `/config`. Merely saving a template from a temporary startup chart does not automatically create a persistent chart: apply it to a normal chart. The usual ongoing opening path needs no custom command. [Platform start](https://www.metatrader5.com/en/terminal/help/start_advanced/start)

If an installer uses `ChartApplyTemplate`, its `true` return means the command was queued, not that the EA initialized successfully. Applying a template can unload the calling EA. It also cannot elevate trading permission: a caller prohibited from trading produces a template-launched EA prohibited from trading even if the template requests permission. Require the target EA's startup acknowledgement rather than assuming installation succeeded. [ChartApplyTemplate](https://www.mql5.com/en/docs/chart_operations/chartapplytemplate)

## Lifecycle and availability

`OnInit` runs after loading and again after input, account, chart symbol/timeframe, and compilation changes. Returning `INIT_FAILED` forcibly removes an EA. Recommendation: initialize a bounded waiting state for temporary disconnection or incomplete history; retry through a timer. Invalid configuration/account identity must block trading, independently of whether the program stays attached to display that status. [Initialization](https://www.mql5.com/en/docs/event_handlers/oninit), [terminal events](https://www.mql5.com/en/docs/runtime/event_fire)

`OnTimer` supports work without new ticks, but a pending/running timer event is not queued again. Keep handlers short; do not use a long blocking warmup or count timer callbacks as elapsed seconds. `OnTick` events can also coalesce. AutoTrading disabled prevents trade requests while the EA continues running, so capture and analysis can remain available with trading disabled. [OnTimer](https://www.mql5.com/en/docs/event_handlers/ontimer), [OnTick](https://www.mql5.com/en/docs/event_handlers/ontick)

`OnDeinit` is limited to **2.5 seconds**. Save important state during operation; shutdown cleanup is only a final attempt. Do not promise that exiting MT5 closes a position: loss of connection, process termination, or an unavailable market can prevent that. Retain verified server-side protection and recover owned positions at the next startup. [Terminal events](https://www.mql5.com/en/docs/runtime/event_fire), [server-side stop orders](https://www.metatrader5.com/en/terminal/help/trading/performing_deals)

## Resume without repeating an old signal

The following are engineering recommendations, not extra trading signals:

1. Start with new entries blocked. Check the expected DEMO identity, symbol contract, permissions and connection; reconcile owned positions, orders, and recent deals before declaring readiness. `TERMINAL_CONNECTED` is a connection flag, not proof that a particular symbol's history and quote are current. [Terminal properties](https://www.mql5.com/en/docs/constants/environment_state/terminalstatus)
2. Rebuild calculations from completed historical data while explicitly disabling historical entry actions. `CopyTicksRange` can return partial data on timeout; validate returned coverage and errors. Resume the capture cursor with overlap and careful deduplication because multiple ticks can share a millisecond. [CopyTicksRange](https://www.mql5.com/en/docs/series/copyticksrange)
3. Persist the last decision bar and trade intent. On cold start/reconnection, catch up analysis, mark already elapsed decisions as skipped, and wait for the next fresh eligible decision. Do not replay missed entries or reset the watermark to zero.
4. Preserve the existing daily risk day/boundary and realized-risk total across app restarts. Reconcile against broker history before resuming; reopening MT5 must not grant another daily loss allowance. Missing/inconsistent state means no new entries until recovered.
5. Persist intent before sending a request, then record its result and reconcile broker state. A crash between server acceptance and local acknowledgement must not produce an automatic resend. An uncertain request remains blocked until resolved. This conservative design may miss a trade; it does not claim exactly-once execution across network failures.

Record `STARTING`, `WAITING_FOR_DATA`, `ANALYZING`, `TRADING_DISABLED`, `RISK_HALTED`, and `DUPLICATE_BLOCKED` states with reasons so an open app is not mistaken for a ready strategy.

## Durable state and duplicate instances

Terminal global variables are shared by MQL programs within one terminal and expire after four weeks without access. They are distinct from ordinary program globals, which do not provide restart persistence. `GlobalVariablesFlush` forces their disk save; relying only on normal terminal shutdown risks losing recent changes after a crash. Keep a versioned durable journal/checkpoint for recovery beyond the global-variable retention period. [Terminal globals](https://www.mql5.com/en/docs/globals), [forced persistence](https://www.mql5.com/en/docs/globals/globalvariablesflush)

Namespace state by server, account, symbol and strategy identity. Keep ownership locks separate from daily risk and decision state. MetaQuotes documents `GlobalVariableSetOnCondition` as atomic compare-and-set suitable for a mutex, and explicitly demonstrates why separate existence checks and unconditional writes race during simultaneous startup. Initialization and release must also be deliberate; only the owner should release its lock. [Atomic global update](https://www.mql5.com/en/docs/globals/globalvariablesetoncondition), [concurrency example](https://www.mql5.com/en/book/common/globals/globals_condition)

A temporary global variable is suitable for a terminal-session lock: it disappears on terminal shutdown and is not written by `GlobalVariablesFlush`. It is unsuitable for risk or decision history. Unexpected EA termination can still leave an in-session lock; do not steal ownership merely because a heartbeat is late. Resolve the owner or remain blocked. A terminal-local mutex does not coordinate separate terminal installations. [Temporary globals](https://www.mql5.com/en/docs/globals/globalvariabletemp)

**The proposed exclusive file handle is also directly supported.** Open a separate namespaced lock file using `FILE_READ|FILE_WRITE|FILE_BIN|FILE_COMMON`, without either sharing flag, and retain the handle throughout operation. The official book explicitly says the first opener receives exclusive access and a second open fails, including another open by the same program. It also states that open files are forcibly closed when the MQL program terminates; explicitly close in normal cleanup. A leftover file's existence is not itself a lock. Check the handle, not `FileIsExist`. [Exclusive access and termination](https://www.mql5.com/en/book/common/files/files_open_close)

`FILE_COMMON` uses the terminals' common files directory. Coordination requires the same resolved directory; separate Wine prefixes may resolve different directories. Validate duplicate-open rejection and reacquisition after removal/restart in the actual installation. An open failure can also mean an I/O error, so block safely and log the error instead of always claiming another instance. [FileOpen](https://www.mql5.com/en/docs/files/fileopen)

For the proposed CSV checkpoint, write a temporary file, flush and close it, then check `FileMove` replacement success. `FileFlush` writes buffered data, and `FILE_REWRITE` permits replacement, but these docs do **not** promise atomic crash-safe transactions. Keep a recoverable prior checkpoint/journal and reject incomplete state; keep the long-held lock in a different file. [FileFlush](https://www.mql5.com/en/docs/files/fileflush), [FileMove](https://www.mql5.com/en/docs/files/filemove)

Position recovery should use strategy Magic plus symbol/account and stable position identifier, then rediscover the current ticket before action. Position tickets can change; fresh selection avoids stale cached data. Symbol-only closing is unsafe when multiple positions exist. [Position properties](https://www.mql5.com/en/docs/constants/tradingconstants/positionproperties), [position selection](https://www.mql5.com/en/docs/trading/positionselectbyticket), [ticket-based close](https://www.mql5.com/en/docs/standardlibrary/tradeclasses/ctrade/ctradepositionclose)

## Deployment evidence to obtain

Check ordinary reopen, offline startup followed by reconnect, an intentional duplicate attachment, and restart after a processed decision. Confirm capture resumes, no historical entry is replayed, risk remains unchanged, only one instance owns execution, and blocked permissions remain visible. Remove the old scheduled launcher/watchdog from the operating design so it cannot reopen or stop this user-opened instance on the former timetable; that transition is implementation work outside this read-only note. Preserve frozen Step 8 separately. No restart tests or trades were performed for this research.

## Follow-up: terminal trading permission after normal reopening

**Parent-reported implementation observations, not reproduced by this research:** normal Mac app reopening now restores the EA, capture, and durable state. State uses terminal-local `MQL5/Files` because `FILE_COMMON` resolved differently for Windows users `aymanaziz` and `user`. A `/config` launch with `[Experts] Enabled=1` and `AllowLiveTrading=1` reports terminal permission 1; normal reopening reports terminal permission 0 while individual EA permission remains 1. The user has authorized continued experimental DEMO operation.

The documented distinction is narrower than “startup settings never persist”: `/config` selects an alternative configuration, and custom configuration files are read-only; UI changes are not written back to that custom file. This does **not** explicitly specify every writeback interaction with the normal configuration. Therefore the observed permission difference supports a configuration-path explanation but does not alone prove its cause. [Custom configuration](https://www.metatrader5.com/en/terminal/help/start_advanced/start)

MetaQuotes identifies `Config/common.ini` as the normal storage for settings in Tools → Options. The toolbar Algo Trading switch and Options → Expert Advisors control terminal-wide trading permission, independently of each EA's permission. This supports setting the main switch through the **normally opened app**, then checking a normal close/reopen; an unconditional persistence guarantee for every Wine/build combination was not found. [Normal settings storage](https://www.metatrader5.com/en/terminal/help/start_advanced/structure), [trading permission controls](https://www.metatrader5.com/en/terminal/help/algotrading/trade_robots_indicators)

Account/profile switches are competing explanations: their protection options deliberately disable automated trading on those changes; changing a chart's symbol/period can disable its EA. Keep these safeguards enabled. Let the intended DEMO account and saved profile finish loading, verify them, enable the main switch once through native UI, and then inspect both permissions after reopening. If it turns off again, compare the normal launch's resolved data path, account/profile transition journal, and saved Expert settings before changing anything else. Do not disable those protections or repeatedly toggle trading from the EA to conceal the cause. [Protective platform settings](https://www.metatrader5.com/en/terminal/help/startworking/settings)

Acceptance requires terminal permission 1 and EA permission 1 after an ordinary reopen **on the verified DEMO account**, with risk state retained and no historical signal replay. Missing broker permission still blocks orders. This follow-up changed only this note; it did not operate the UI, edit settings, or trade.
