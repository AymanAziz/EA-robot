# Step 8 continuation: historical clock, generated ticks and exit attribution

Research checked: **2026-11-12**. Scope: engineering qualification of the frozen H01 implementation during January–February 2024. This note changes no strategy rules, gates, frozen artifacts or terminal state. No strategy tests or holdout access were performed for this research.

## Finding

A broker-history Strategy Tester comparison can legitimately use **Model=0, Every tick generated from broker M1 history**, provided both implementations consume the same captured simulated stream and the result is explicitly limited to engineering parity. It cannot establish execution on actual historical Bid/Ask ticks. February 2024 is an implementation exercise because H01 has historical trades there; choosing that active window does not create independent performance evidence.

The available clock comparison strongly supports UTC+2 for the bounded January 22–February 29, 2024 interval. It is empirical evidence, not a published JustMarkets DST rule. The reason for any final forced liquidation must be reconciled separately from SL, TP and strategy exits.

## Clock evidence and limits

The currently accessible JustMarkets commodities page identifies its displayed schedule as server GMT+2. It does not publish a February 2024 Demo6 offset or a historical transition table. Bounded searches of official JustMarkets domains found no dated policy establishing that interval. A search-indexed EU MT5 Live maintenance announcement for March 30, 2024 mentioned GMT+2, but the page now returned 404; a maintenance schedule for another server would not establish Demo6 history anyway. The current November observation cannot itself prove a past offset. [JustMarkets commodities](https://justmarkets.com/markets/commodities).

Inside the tester, `TimeGMT()` equals simulated `TimeTradeServer()`. Their difference therefore cannot recover historical UTC offset. Keep raw server timestamps and a separately evidenced conversion; apply it once. [MetaQuotes TimeGMT](https://www.mql5.com/en/docs/dateandtime/timegmt).

The existing local [clock result](../goldnix_step8_h01/out/S8P_20261112T153727Z/CLOCK_CHECK.json) compares native broker H1 Bid closes against the independent public **H1** source, not M5-derived candles. It tests offsets 0–4 hours using consecutive-hour log returns and reports every offset's coverage. At +2 hours:

- 636 matched returns; pooled correlation **0.999596** and median absolute close difference **0.06 gold price units**.
- Six weekly correlations range **0.999410–0.999740**.
- Neighboring +1/+3 hour correlations are approximately **0.0076/0.0101**, with median close differences **1.14/1.12**.

Those large, consistent separations support a bounded engineering conversion. They do not prove identical prices, tick ordering, historical spread, or offsets outside this interval. The source hashes and registered diagnostic criteria are preserved in the result and its [probe record](../goldnix_step8_h01/out/S8P_20261112T153727Z/STARTED.json).

For any additional clock diagnostic, freeze its method before looking at strategy outcomes: compare like Bid prices; aggregate complete UTC M5 groups into H1 if using M5; retain gaps; test the fixed offset grid; report per-week return correlation and separate open/high/low/close errors. Returns avoid the misleadingly high correlation that trending price levels can create. Prefer a common matched intersection across offsets, or disclose differing coverage as the present report does. Treat OHLC error as a cross-feed diagnostic, not an expectation of exact equality. Select no offset by P&L, trade count or gate outcome. A non-unique or inconsistent winner remains unresolved.

## Historical tick coverage

The [native probe metadata](../goldnix_step8_h01/out/S8P_20261112T153727Z/meta.csv) records 665 H1 bars, a server series start in 2011, and **zero requested ticks with error 0** for the February 15, 2024 query identified by the probe. This establishes that the request returned no ticks; it does not establish the first available tick date for the symbol or the absence of ticks on every February day. H1 availability cannot establish tick availability.

No public official JustMarkets guarantee of Cent `XAUUSD.c` tick coverage back to February 2024 was found. `CopyTicksRange` uses inclusive millisecond bounds, can return partial history on a synchronization timeout, and exposes errors that must accompany the returned count. Coverage evidence requires the exact server, symbol, bounds, error, count, first/last timestamp and gaps. [MetaQuotes CopyTicksRange](https://www.mql5.com/en/docs/series/copyticksrange).

## Generated stream: usable for engineering, with explicit assumptions

MetaQuotes explicitly documents that `CopyTicks` in **Every tick** mode returns generated history, limited to the latest **128,000 ticks**. The release note says Open prices only and 1 minute OHLC do not create that tick history. Current runtime documentation reserves retrieval beyond the cache for real-tick testing. Thus an end-of-month `CopyTicks`/`CopyTicksRange` request is not a durable archive of all generated ticks. The exact generated-history statement names `CopyTicks`; do not assume `CopyTicksRange` bypasses the cache. [MetaQuotes build 1375 release notes](https://www.metaquotes.net/en/metatrader5/news/page6), [testing runtime](https://www.mql5.com/en/docs/runtime/testing).

For Model=0, Bid follows the generated M1 path; Ask is Bid plus that minute bar's fixed spread. Actual intraminute spread changes are absent. If the historical spread is nonpositive, the agent uses the last known spread. This creates simulated Bid/Ask quotes, not recovered historical Ask observations. [Real and generated ticks](https://www.metatrader5.com/en/terminal/help/algotrading/tick_generation), [spread simulation](https://www.mql5.com/en/docs/runtime/testing).

The documented Every tick model calls `OnTick` at each generated control point. Recommended evidence capture is therefore the processed `SymbolInfoTick` record in each callback, with a monotonically increasing sequence, millisecond timestamp, Bid, Ask and flags. Preserve multiple records sharing a timestamp. Export before trading logic returns early, buffer writes, and retain terminal build, symbol specification, M1 bars/spreads, configuration and file hashes. Compare exported counts and interval boundaries with the tester journal; reconcile rather than silently discard differences. [Testing runtime](https://www.mql5.com/en/docs/runtime/testing), [tester journal](https://www.metatrader5.com/en/terminal/help/algotrading/tester_journal).

Python replay should consume that exact captured sequence and reproduce the frozen H01 signal-price definition. Averaging separately aggregated Bid/Ask highs is not generally equivalent to taking the high of tick midpoints. Any different representation must be identified as an implementation difference. Passing parity on generated ticks demonstrates agreement under the documented generator and spread assumptions; it does not remove uncertainty about real intraminute chronology or historical broker costs.

## Exit attribution and the test boundary

`DEAL_REASON_SL` and `DEAL_REASON_TP` explicitly identify stop and target activation. `DEAL_REASON_EXPERT` identifies an order originating from an MQL program; it does not distinguish the program's Friday flatten from another programmed exit. `DEAL_ENTRY` identifies entry/exit/reversal, and `DEAL_POSITION_ID` links deals across a position. Exit `DEAL_SL`/`DEAL_TP` retain the position's levels at closure. The official reason enumeration contains **no dedicated end-of-test reason**. [MetaQuotes deal properties](https://www.mql5.com/en/docs/constants/tradingconstants/dealproperties).

The official references examined do **not** establish a universal enum value, exact fill timestamp/price or callback ordering for final tester liquidation. `OnTester` is documented as an after-testing handler; `TesterStop` performs normal early completion and submits accumulated statistics, without specifying those liquidation details. Do not invent a universal mapping from these descriptions. [OnTester](https://www.mql5.com/en/docs/event_handlers/ontester), [TesterStop](https://www.mql5.com/en/docs/common/testerstop).

For the actual build, preserve complete final deals, report and agent journal alongside the EA request ledger. Link exits by position/order/deal IDs. Record native reason and comment unchanged; distinguish explicit SL/TP, logged strategy exits, and journal-confirmed boundary liquidation. Do not label a losing close as SL or assume all non-SL/TP closes are strategy exits. Reconcile final report totals against callback exports because documentation reviewed here does not guarantee that a callback-only ledger includes every terminal cleanup transaction.

H01's frozen [protocol](../goldnix_mtf2/replay_protocol.json) already defines Friday 20:00 UTC flatten and end-of-era closing. A shorter engineering window introduces its own boundary: compare both implementations at the same cutoff, disclose any open position and boundary liquidation separately, and do not move that cutoff to improve results. Unresolved cleanup differences should remain explicit qualification gaps.

## Follow-up: zero opening-deal time

Checked 2026-11-12 after the native run reported correct closing times but zero opening times. **The documented contract does not establish that reading a later deal invalidates an earlier ticket in the selected list.** `HistorySelectByPosition` builds the position's deal list. `HistoryDealGetTicket(index)` selects an element for processing and is the recommended iterator. The explicitly documented list resetter is `HistoryDealSelect(ticket)`, which replaces the list with one deal; another history selection can also replace the context. [HistorySelectByPosition](https://www.mql5.com/en/docs/trading/historyselectbyposition), [HistoryDealGetTicket](https://www.mql5.com/en/docs/trading/historydealgetticket), [HistoryDealSelect](https://www.mql5.com/en/docs/trading/historydealselect).

The AlgoBook requires the requested ticket to be available in the selected history context. Its ticketed getter returns zero on error; the boolean/output overload exposes success separately, with `_LastError` providing the error. It does not impose a rule that only the most recently iterated deal may be read. [Reading deal properties](https://www.mql5.com/en/book/automation/experts/experts_historydealget_funcs).

The inspected `Reconcile`, `RollDay` and `Persist` implementations contain no documented history-reset call between enumeration and the opening-time read. Therefore **the exact failure cause remains unproven**. A 1969-12-31 22:00 UTC export is consistent with subtracting 7,200 seconds from a zero raw timestamp; it is not evidence of historical clock misalignment.

Recommended diagnosis: record opening/closing tickets, selected-list count, the boolean getter result, raw timestamp and immediately captured error after `ResetLastError`. Validate the iteration's ticket and `DEAL_ENTRY` reads too; failed reads must not become valid entry classifications. Copying needed properties while enumerating avoids a deferred dependency. Alternatively, explicitly select the saved opening ticket **after** enumeration, read/check its fields, then separately select/read the closing ticket. Do not call the single-deal selector inside a list loop. These are defensive approaches; only a controlled native check can establish which condition caused this run's failure. No implementation or terminal action was performed for this follow-up.
