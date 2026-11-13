# GOLDNIX: qualifying an accessible small-contract demo

Step 6 remains unapproved. This work makes the account-access route concrete and
adds a tested read-only qualifier; it does not change the strategy, equity,
statistical thresholds, or prior evidence. No further strategy variants were
tested. The explicit research history remains 68 variants.

## Actual result

**JustMarkets-Demo6 now passes the XAUUSD.c contract screen.** The fresh MT5
snapshot evaluated at 2026-11-12 08:08:25 UTC confirms a connected demo hedging
account, **2,000 USC = $20** equity/free margin, and a minimum volume of
**0.01 lot with a 1 oz contract size: 0.01 oz minimum exposure**.

At that minimum volume, MT5 calculated **1 USC ($0.01) loss for a $1 adverse
gold-price move**, in both directions, and **1.32 USC ($0.0132) margin**.
The unchanged S11 distribution projects **$1.01213 conditional p99 annual
drawdown**, below the fixed **$2.40 limit**. Broker stop distance is zero.
XAUGBP.c and XAUJPY.c remain unqualified because this study requires XAU/USD
quote economics. **This account screen does not approve Step 6.**

The exporter ran with automated trading disabled and submitted no orders.
It captures no account names, login identifiers, or passwords. The earlier
MetaQuotes result is preserved in `out/current`: its 1 oz minimum exposure and
$39.73 margin failed the original $20 account screen.

This is dated account evidence. Re-running the importer against an old snapshot
does not refresh it: both the capture and quote must be current within five
minutes when evaluated.

## User-requested demo trade

After the account screen, the user explicitly requested an executed trade.
On 2026-11-12 at 08:23:40 UTC, `DemoRoundTrip.mq5` opened one **0.01-lot BUY
on XAUUSD.c at 3953.73** and closed it three seconds later at **3953.42**.
The entry deal is **113712320**, the exit deal is **113712380**, and the position
ticket is **136635171**. Both requests returned broker execution code 10009.

Net result: **−0.31 USC (−$0.0031)**, with zero commission, swap, and fee on the
two recorded deals. The resulting demo balance is **1,999.69 USC**. The earlier
qualification snapshot above retains its original pre-trade 2,000 USC balance.
This was an entry/exit execution test with no strategy signal.

The script requires a matching explicitly supplied account identifier, demo
account mode, JustMarkets-Demo6, USC currency, hedging mode, and the verified
0.01-lot minimum. It persists an entry marker before sending its single BUY
request; reusing that run cannot open another position. Closing is restricted
to its own marked position. Its default inputs cannot place an order.

A separate read-only script verified the broker history after restarting MT5:
**one entry, one exit, zero positions, zero pending orders**, and both terminal
and script automated-trading permission disabled. The one-off launch was
returned to read-only operation and its private parameter file removed.
Both scripts compiled with zero errors and zero warnings.

- [Trade receipt](out/demo_trade_20261112T082301Z/RECEIPT.json)
- [Execution audit](out/demo_trade_20261112T082301Z/execution.csv)
- [Independent history and permission verification](out/demo_trade_20261112T082301Z/post_restart_verification.csv)
- [Execution source, compiler logs, and manifest](out/demo_trade_20261112T082301Z/)

### One-minute demo execution

The user next requested a smaller timeframe and a quick result. A separate
run on **M1** opened **0.01 lot BUY at 3941.52** at 08:43:46 UTC and used a
60-second time exit, closing at **3942.08** at 08:44:46 UTC. The protective
stop-loss was 3940.08 and was not triggered. The broker recorded **+0.56 USC
(+$0.0056)** net profit, with zero commission, swap, and fee. The resulting
demo balance is **2,000.25 USC**.

The script now accepts a bounded hold duration of 1–300 seconds and can require
an exact chart timeframe before entry. This run verified `PERIOD_M1`, one entry,
one exit, and a 60-second interval in the broker's deal timestamps. Entry deal:
**113799593**; exit deal: **113802537**; position: **136734279**. A read-only
restart independently verified the history and restored automated trading to
off, with no open positions or orders.

This is a single timed execution result with no strategy signal. The frozen
H1 strategy parameters and Step 6 gates were not changed.

- [M1 trade receipt](out/demo_trade_M1_20261112T084229Z/RECEIPT.json)
- [M1 execution audit](out/demo_trade_M1_20261112T084229Z/execution.csv)
- [M1 independent history and permission verification](out/demo_trade_M1_20261112T084229Z/post_restart_verification.csv)

### Bounded M1 demo batch

The next request authorized more demo executions. `DemoBatch.mq5` ran the same
0.01-lot BUY test, one position at a time, with a 60-second target exit and a
broker stop-loss. The stated limits were 30 trades or 30 minutes, stopping new
entries after a realized batch loss of 20 USC. A stop file also blocks entries
and requests closure of the script's own position. Each trade retains its
persistent entry marker, so recovery cannot repeat its BUY.

On 2026-11-12 the batch opened **12 trades: 7 gains and 5 losses**, for a net
**−0.26 USC (−$0.0026)**. The balance moved from **2,000.25 to 1,999.99 USC**.
Nine trades used timed exits and three closed at their broker stop-loss.
Recorded commission, swap, and fees were zero. Maximum realized drawdown
within this batch was 2.04 USC.

The batch stopped early because the Mac entered **Clamshell Sleep at 17:31:24
Malaysia time** during trade 12. MT5's timed close then failed with code 10031
(no connection). The broker stop-loss closed that position at 3936.63, for
−1.38 USC, **382 seconds** after its 3938.01 entry. The raw batch log initially
contained only 11 completed trades; reconciliation preserves that interruption
and includes the final trade from broker history. No new entries were sent
during recovery. Local timed exits require the Mac to remain awake and connected;
the server-side stop-loss remained effective while MT5 was disconnected.

`VerifyDemoBatch.mq5` independently matched all 24 entry/exit deals and their
position IDs after restart: **12 entries, 12 exits, zero positions and orders**,
with automated trading disabled. All three native scripts compiled with zero
errors and warnings. This repeated execution test uses no strategy signal and
does not change the frozen H1 research or approve Step 6.

- [Batch report and all trades](out/demo_batch_M1B_20261112T091641Z/SUMMARY.md)
- [Complete receipt](out/demo_batch_M1B_20261112T091641Z/RECEIPT.json)
- [Independent broker history](out/demo_batch_M1B_20261112T091641Z/post_restart_history.csv)
- [Interruption and recovery](out/demo_batch_M1B_20261112T091641Z/RECONCILIATION.json)

## Independent M5 sessions

`demo_session.py` installs and runs `DemoSession.mq5` as a bounded local demo
execution test. macOS launchd owns the controller independently of the chat
session. It makes no AI/API calls and does not require an AI model to supervise
each trade. The existing Wine/MT5 installation and authenticated demo account
are required; no passwords or account numbers are written into the reports.

Default rules: **M5, 0.01-lot BUY, one position at a time, five-minute target
exit, broker stop-loss, up to three hours / 36 attempts**. Entries are spaced at
least one five-minute slot apart after an early stop-loss. New entries stop at
20 USC realized batch loss, a stop request, a detected clock gap/disconnection,
or any account/execution mismatch. The loss threshold is not a guaranteed loss
cap. The final slot is skipped if its full hold would exceed the deadline.

The controller keeps an idle Mac awake for the job's lifetime. **Keep the lid
open, power connected, MT5 running, and the internet connected.** Closing the
lid or powering off still interrupts local timed exits. Every order includes a
server-side stop-loss. On interruption the controller blocks new entries,
attempts only closure/reconciliation of the existing marked position, and
restores read-only operation. A persistent session marker prevents replaying
the entry session. Failed/offline verification is reported as
`needs_reconciliation`, never as successful completion.

```sh
.venv/bin/python -m goldnix_venue.demo_session prepare --minutes 180
# Use the output directory printed by prepare:
.venv/bin/python -m goldnix_venue.demo_session start '/absolute/output/directory'
.venv/bin/python -m goldnix_venue.demo_session status '/absolute/output/directory'
.venv/bin/python -m goldnix_venue.demo_session stop '/absolute/output/directory'
```

`prepare --minutes 6 --check-only` exercises the native stop gate and automatic
cleanup without opening trades. The native integration check completed with
zero entries/exits, no positions/orders, and both automated-trading flags off.
Thirteen Python checks cover the archived broker history, changed closing magic,
duplicate deal replay, incomplete positions, account identity, offline/live
account rejection, cent conversion, and balance reconciliation.

`out/LATEST_SESSION.json` points to the current session. During the run,
`STATUS.json` contains the deadline and confirmed realized result. On completion,
`SUMMARY.md`, `RECEIPT.json`, `trades.csv`, `final_history.csv`, and
`final_bars.csv` contain the result and M5 prices for later analysis. Sources,
compiled binaries, compiler logs, raw audits, and a hash manifest accompany the
report. These timed BUYs are execution tests with no strategy signal; they do
not approve Step 6 or establish profitability.

## Connected account and remaining evidence

The account holder supplied an existing Cent demo. MT5's company search loaded
Just Global Markets Ltd. and its server list; the terminal then authenticated
JustMarkets-Demo6. Its saved startup configuration still named the removed
MetaQuotes account. The account-selection fields were corrected locally, with
a private backup inside the terminal's Wine prefix. The final restart used
saved account settings without a login/server override and authenticated the
same JustMarkets demo. Credentials are not stored in this repository.

The [earlier access research](../docs/GOLDNIX_DEMO_ACCESS_RESEARCH_20261112.md)
records the public-documentation uncertainties before this actual account was
available. This terminal capture resolves the account-access and minimum-size
questions for this demo. Historical venue transaction costs and independent
strategy validation remain outstanding.

## Qualifier behavior

The public interfaces remain exported CSV → qualification report and one broker
snapshot → one contract result. The new module is separate because all previous
research sources and artifacts are preserved by their existing manifests.

- Export every contract with base currency XAU, including unknown profit
  currencies. An unknown or unsupported unit produces an explicit rejected row.
- Convert USD and USC **account-money** values once. Both hypothetical loss
  directions are calculated at the actual minimum volume; use the worse result.
  Non-USD profit currency requires separate quote-unit evidence and is not
  automatically divided by 100.
- Keep the study budget at `min(actual USD equity, $20)` and usable margin at
  the smaller of that budget and actual free margin. A large default demo balance
  cannot inflate G7's allowance.
- Require successful calculations, current quotes/capture, a real server symbol,
  a demo hedging account, both trading directions, positive finite economic
  inputs, and broker stop limits compatible with the existing $0.50 stop floor.
- Retry calculations for up to approximately 30 seconds per symbol after quotes
  become available. A successful MT5 API return can still contain zero values
  while account-currency conversion data loads. Export `OK` only for finite,
  negative adverse-move profits and positive margins; otherwise retain an
  explicit unavailable/failed row. Record attempt count and elapsed wait.
- Keep `step6_approved: false` even if the contract screen passes. A snapshot
  cannot prove historical transaction costs or independent strategy evidence.

`OrderCalcProfit` and `OrderCalcMargin` return account-currency amounts; the
margin calculation treats the proposed order separately from existing orders
and positions. The symbol and account properties provide the contract units,
trading modes, and stop/swap metadata.
[Profit calculation](https://www.mql5.com/en/docs/trading/ordercalcprofit),
[margin calculation](https://www.mql5.com/en/docs/trading/ordercalcmargin),
[symbol properties](https://www.mql5.com/en/docs/constants/environment_state/marketinfoconstants),
[account properties](https://www.mql5.com/en/docs/constants/environment_state/accountinformation).

The existing Step 6 numerical model remains spread-based. The captured swap
fields are additional venue evidence; they were not silently introduced into
the frozen gate calculation. Commission history and actual historical bid/ask
costs are not supplied by this snapshot. S11 remains an exploratory candidate
with a negative search-adjusted lower bound and no untouched validation result.

## Repeat the verified account check

`ExportGoldVenue.mq5` and its compiled script are installed under
`MQL5/Scripts/Goldnix` in the existing terminal. Run the read-only script on the
candidate gold chart, with automated trading disabled. The supplied
`run_export.ini` uses the verified `XAUUSD.c` chart and leaves MT5 open. Its symbol
must match the intended server before an automated startup is used. It never
changes the account login.

The script writes `Common/Files/goldnix_venue_qualification.csv`. Import the fresh
file within five minutes using a new output directory:

```sh
PYTHONPATH=.:goldnix .venv/bin/python -m goldnix_venue.qualification \
  '/absolute/path/to/Common/Files/goldnix_venue_qualification.csv' \
  --output goldnix_venue/out/new_account_check
```

The importer authenticates the original research and all three completed
research-round manifests, copies the raw export and exact source snapshot,
and refuses to overwrite an existing output directory. A failed contract
screen stays a failed result.

## Validation

The first JustMarkets export was rejected because MT5 returned `true` with
zero profit, tick-value, and margin calculations immediately after login.
`ProbeCentEconomics.mq5` reproduces the calculation path over 60 seconds at
minimum, 1, and 100 lot volumes, without submitting orders. At the minimum
volume, the initial zero became a 1 USC loss and 1.32 USC margin after five
seconds and remained stable through the later samples. The catalog also
records the initially unselected `USDUSC` conversion symbol.

The exporter now waits for usable calculations. Its cold-start regression run
required **2 calculation attempts / 259 ms**, exported positive economics, and
passed qualification. Both scripts compiled with **0 errors and 0 warnings**.
This native startup behavior was tested in MT5; the Python tests cover the
import and qualification boundary.

Current Python verification:

```text
27 passed in 0.02s
```

New behavior tests cover USD/USC conversion, asymmetric BUY/SELL economics,
invalid and nonfinite evidence, stale/future timestamps, broker stop distance,
fixed $20 budgeting on a larger demo, and explicit handling of rejected CSV rows.
These synthetic fixtures test the software. The separate native integration
check supplies the real JustMarkets account evidence. Prior research manifests
were authenticated by the qualification command; strategy gates were unchanged.

- [Verified JustMarkets qualification](out/justmarkets_cent_verified_20261112T080825Z/QUALIFICATION.json)
- [Actual broker snapshot](out/justmarkets_cent_verified_20261112T080825Z/snapshot.csv)
- [Native and Python verification](out/justmarkets_cent_verified_20261112T080825Z/VERIFICATION.json)
- [Exporter compiler log](out/justmarkets_cent_verified_20261112T080825Z/cent_export_fixed_compile.log)
- [Warmup diagnostic and original source snapshot](out/justmarkets_cent_warmed_20261112T080326Z/)
- [Initial zero-result rejection](out/justmarkets_cent_20261112T075559Z/QUALIFICATION.json)
- [Earlier MetaQuotes qualification](out/current/QUALIFICATION.json)
