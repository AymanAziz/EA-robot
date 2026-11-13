# Native MT5 engineering preparation for Step 8

Checked **2026-11-12** against official MetaQuotes and JustMarkets sources.
Research only: no terminal launch, configuration change, tick export, strategy
run or order was performed for this note. H01 still lacks its own Step 7
qualification; an authorized implementation/replay check does not complete
that prerequisite or establish profitability.

## Isolated launch and configuration

MetaQuotes documents Windows `/config:` and `/portable` switches. In portable
mode, data resides under the writable installation directory. `Expert` is
relative to `MQL5\Experts`; the official example omits `.ex5`.
`ExpertParameters` names a file under `MQL5\Profiles\Tester`. Missing inputs
can fall back to a previous set or compiled defaults: verify the loaded values.
[Official launch/configuration reference](https://www.metatrader5.com/en/terminal/help/start_advanced/start).

Illustrative configuration, **not written to MT5 or executed**:

```ini
[Experts]
Enabled=0
AllowLiveTrading=0
AllowDllImport=0

[Tester]
Expert=Goldnix\H01Engineering
ExpertParameters=H01_frozen.set
Symbol=XAUUSD.c
Period=M5
Model=4
Optimization=0
ForwardMode=0
ExecutionMode=0
FromDate=2025.10.01
ToDate=2025.12.31
Deposit=2000
Currency=USC
Leverage=<VERIFIED_ACCOUNT_LEVERAGE>
UseLocal=1
UseRemote=0
UseCloud=0
Visual=0
Report=reports\H01_unique_run.htm
ReplaceReport=0
ShutdownTerminal=1
```

`Model=4` requests real ticks; `Model=0` generates every tick. Dates use
`YYYY.MM.DD`. `ExecutionMode=0` has no simulated delay; `-1` means random delay,
positive values milliseconds. `Report` is relative to the platform directory;
its parent must exist. `ShutdownTerminal=1` exits after completion, but manual
stopping resets it. `[Tester] Login` is an emulated account identifier, not
broker authentication. These keys are documented in the
[same reference](https://www.metatrader5.com/en/terminal/help/start_advanced/start).

**Engineering recommendations:** use a separate terminal installation/data
directory and preferably a separate Wine prefix; do not launch against a
running shared terminal or copy active trading-chart profiles. Set leverage
from captured specifications, and prove that `2000 USC` produces the intended
`$20` test economics. If USC conversion is unsupported, report failure instead
of silently changing currency. Use unique report/artifact names. Require a
completion marker, intended-input dump, actual time range and report, rather
than treating process exit alone as success.

MetaQuotes' macOS distribution uses Wine; its documentation gives the Wine
data-folder layout. It does not establish that an arbitrary Wine build has a
fully headless, unattended tester interface.
[Official macOS installation](https://www.metatrader5.com/en/terminal/help/start_advanced/install_mac).
The Windows command shape to pass through the existing Wine launcher is:

```text
terminal64.exe /portable /config:C:\MT5-Research\step8.ini
```

Resolve actual Wine/Windows paths locally; keep the isolated installation's
working directory explicit. No Wine installation or prefix change is proposed
as a prerequisite without first checking the existing working environment.

## Tester trading while online Algo Trading remains disabled

The official MQL5 book states that `TERMINAL_TRADE_ALLOWED` and
`MQL_TRADE_ALLOWED` are true in the tester. Therefore online Algo Trading need
not be enabled to simulate trades. A separate EA should reject initialization
unless `MQLInfoInteger(MQL_TESTER)` is true, and every order path should remain
within that tester-only boundary. Do not attach it to an ordinary demo chart.
[Permissions](https://www.mql5.com/en/book/common/environment/env_permissions),
[tester-mode property](https://www.mql5.com/en/docs/constants/environment_state/mql5_programm_info).

`OnTick` notifications occur regardless of the online AutoTrading button.
However, a new tick event is not queued if one is already queued/processing;
the general API does not promise one callback per archived quote. Keep handlers
short and compare observed counts rather than assuming callback completeness.
[OnTick semantics](https://www.mql5.com/en/docs/event_handlers/ontick).
These documented semantics support `Enabled=0` for online protection; the
installed build still needs a tester-only engineering smoke check, with its
permission flags logged.

## Exporting bid/ask history and establishing actual coverage

For bounded native export, use
`CopyTicksRange(symbol, ticks, COPY_TICKS_ALL, from_msc, to_msc)` with a dynamic
`MqlTick[]`. Both endpoints are inclusive milliseconds; request non-overlapping
chunks `[start, end-1]`. Returned records are oldest first. Capture count and
`GetLastError()` for each chunk: timeout or small-buffer results can be partial,
and zero rows are not proof of a market closure.
[CopyTicksRange](https://www.mql5.com/en/docs/series/copyticksrange).

Preserve `time`, `time_msc`, `bid`, `ask`, `last`, `volume`, `volume_real`,
`flags` and original row order. Multiple distinct ticks can share one
millisecond; do not deduplicate on timestamp alone.
[MqlTick structure](https://www.mql5.com/en/docs/constants/structures/mqltick).
Unchanged tick fields carry their last known values. Synchronization can
download missing broker history, and `CopyTicks` may return partial data after
waiting up to 45 seconds in an EA/script. Avoid unbounded/default recent-tick
queries when the intended window is explicit.
[CopyTicks synchronization](https://www.mql5.com/en/docs/series/copyticks).

Before replay, create a coverage manifest: requested and returned limits,
rows/bytes/hash per chunk, duplicate/backward records, invalid/zero/crossed
quotes, largest gaps, daily counts, and correspondence with M1 bars and known
sessions. Preserve failures; do not fill gaps with invented quotes. A 2025 Q4
window is a proposed engineering period only, conditional on actual coverage.
History availability has **not** been probed by this research.

`Model=4` is not proof of entirely observed ticks. MT5 can replace a minute's
ticks when they disagree with its M1 OHLC/volume, or generate ticks where minute
bars lack ticks. The tester's `CopyTicks` database is not subjected to those
minute-bar corrections, so a raw export and the processed tester stream can
diverge. Record both where exact replay is claimed.
[Official runtime/testing details](https://www.mql5.com/en/docs/runtime/testing).

Archive the terminal and agent journals, including real-tick start and
consistency diagnostics. The tester may shift the actual start forward for
insufficient warm-up history; it may also download history beyond the evaluation
window. A config date is not a complete coverage certificate or download fence.
[Tester journal](https://www.metatrader5.com/en/terminal/help/algotrading/tester_journal),
[history preparation](https://www.metatrader5.com/en/terminal/help/algotrading/test_preparation).

## Time, DST and candle construction

In the tester, `TimeGMT()` equals simulated `TimeTradeServer()`; subtracting
them cannot recover historical broker UTC offset. Preserve raw timestamps and
declare a verified conversion before applying UTC Friday, holiday or daily-halt
rules.
[TimeGMT](https://www.mql5.com/en/docs/dateandtime/timegmt).
The Python integration separately describes its timestamps as UTC and requests
UTC-aware datetimes; do not apply an additional broker offset to already-UTC
exports merely because a native chart displays server time.
[Python timestamp contract](https://www.mql5.com/en/docs/python_metatrader5/mt5copyticksrange_py).

**Exact JustMarkets DST intervals remain unverified.** A bounded official-source
search found no dated 2025/2026 transition table identifying U.S. versus
European change dates for `JustMarkets-Demo6`. The freshly opened commodities
page, redirected by the provider to its Indonesia domain, states GMT+2;
older indexed versions state GMT+3. Neither supplies transition instants.
[Current provider trading hours](https://justmarketsidn.pro/markets/commodities).

| Interval | Supported server-to-UTC mapping |
|---|---|
| 2025, including Q4 | Not established by retrieved primary evidence. |
| 2026 before the observed export | Not established; do not infer an annual DST policy. |
| 2026-11-12 parity-export capture | Observed offset `+7200` seconds; valid as dated point evidence. |
| Other/future intervals | Require explicit interval evidence; no extrapolation claimed. |

The point observation is in the
[existing native metadata](../goldnix_mtf/parity/out/MTF_PARITY_20261112T134656Z/meta.csv).
Proceeding with an assumed historical offset can support a labelled engineering
sensitivity, but not exact UTC parity. Do not silently use another broker's DST
calendar or choose the offset that improves performance.

For tick-built bars, freeze intervals, use first/maximum/minimum/last observations,
and expose only completed bars. A boundary starts trading at the first available
quote, not necessarily the exact wall-clock minute.
[Bar/tick timing](https://www.mql5.com/en/docs/runtime/testing).

Preserve the frozen H01 price definition. The high of tick midpoints
`max((bid+ask)/2)` generally differs from `(max(bid)+max(ask))/2`; lows have the
same issue. Aggregate bid and ask separately before averaging if that is the
reference representation. A switch to true tick-midpoint extrema is a disclosed
representation change, not automatic indicator parity. Validate bars, signals,
order intentions and fills separately; keep execution on the appropriate bid
or ask. None of these engineering checks supplies missing Step 7 evidence.
