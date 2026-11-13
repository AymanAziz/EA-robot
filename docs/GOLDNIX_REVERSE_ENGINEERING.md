# GOLDNIX / Life Changer EA reverse-engineering assessment

The supplied archive, a strongly matching public source-code lineage, and
MetaQuotes' official MQL4 documentation were checked on 2026-11-07. This was a
static inspection only: the EX4 was not executed, no broker terminal was opened
and no credential was read.

## Verdict

The archive contains a compiled MetaTrader 4 Expert Advisor and four input
presets, but not its MQL4 source. MetaQuotes documents the build workflow as
compiling an MQL4 program into an executable file with the `EX4` extension. It
separately describes `MQ4` files as source and `EX4` files as executables
compiled from them. The supplied EX4 can therefore be identified as a program
artifact, not treated as the missing source.
[MQL4 programs](https://docs.mql4.com/runtime),
[MQL4 file structure](https://docs.mql4.com/mql4changes)

The core technique can nevertheless be reconstructed with high confidence.
The EX4 identifies itself internally as `Life Changer EA`, links to
`www.lifechangerea.com`, and reports version `1.00`. The explanation video
shows the matching on-chart phrase `Change The Life With Life Changer EA`.
A public, apparently decompiled Life Changer source listing contains the same
identity, interface and dashboard, while a 2019 MetaQuotes forum log records
the exact GOLDNIX default input sequence under another filename, `Profit Maker
EA V2`. Together these are much stronger evidence than parameter names alone.
[Matching 2019 input log](https://www.mql5.com/en/forum/311609),
[public Life Changer code preview](https://mql-files.ru/product/life-changer-ea-1-mq4-4600)

The reconstructed method is:

1. calculate a hand-coded 70-period Aroon Oscillator from the relative recency
   of the highest high and lowest low;
2. open the first BUY when it crosses above +50, or the first SELL when it
   crosses below -50;
3. if price moves adversely, add BUY layers lower or SELL layers higher at the
   configured `Step` distance;
4. geometrically increase later lots using `Multiplier` and move a multi-order
   basket toward a shared recovery target; and
5. use the configured stop, target and trailing logic for protection and exit.

This is an adverse-move recovery grid with martingale-style sizing. It is not
machine learning, a neural network, an LLM, or an AI model. The public source
does not authenticate the exact encrypted payload byte-for-byte, so individual
hidden constants and guard code still require controlled runtime confirmation.

No performance claim follows from these files. In particular, the readme's
deposit and leverage suggestions are not proof of safety, profitability, a
win rate above 50%, or an average USD 20 weekly profit.

## Evidence boundaries

This report keeps three kinds of statement separate:

- **Official platform fact** means a behavior documented by MetaQuotes and is
  followed by a first-party link.
- **Artifact fact** means a value or file observed directly in this archive.
- **Artifact-specific inference** means a proposed explanation of those facts;
  its confidence is stated and it remains falsifiable by a controlled test.

## Inspected evidence

The original ZIP is 160,451,701 bytes with SHA-256
`9502f5c1ea73c226af0462ebde765bcd2dabb0cd5dcd29ff2e93a66a60dc6189`.
Its relevant contents are:

- `robot ea/GOLDNIX EA.ex4`, 59,990 bytes, SHA-256
  `30bb68b79c2c5ac95aed38db28b0e6e4d634e4389ade441e27f566d4e1af2217`;
- four plain-text `.set` files under `preset gold/`;
- `Read me first.TXT`, one DOCX setup guide and three MP4 videos.

There is no `.mq4` or `.mqh` file in the archive. The documented MetaEditor
workflow edits source and then recompiles it to obtain a new EX4; MetaQuotes
does not document an EX4-to-MQ4 source-recovery workflow on these pages.
[MetaTrader 4 script creation and editing](https://www.metatrader4.com/en/trading-platform/help/autotrading/scripts/scripts_create)
Accordingly, the exact original source, source comments, names of internal
variables and original control structure cannot be established from this
archive. This is a limit of the available evidence, not a claim that every
conceivable decompilation attempt is mathematically impossible.

## Identity and lineage

The following independent matches make the lineage conclusion unusually
strong:

- the EX4 header contains `Life Changer EA`, `www.lifechangerea.com` and
  version `1.00`, despite the file being named `GOLDNIX EA.ex4`;
- the EX4 declares Simplified Chinese code page 936, consistent with the
  Chinese identifiers/comments in the recovered source family;
- `goldmaster explain.mp4` shows the exact footer `Change The Life With Life
  Changer EA` while the Navigator and Properties dialog call it `GOLDNIX EA`;
- before a setfile is loaded, that video shows `0.01`, `1.11`, `15`, `30`,
  `400`, `50`, `1234567`, trailing `12/1`, 13 FX symbol slots,
  `MaxPairTrades=2`, `comment=Life Changer EA`, and the time filter enabled;
- the 2019 `Profit Maker EA V2` journal has the same unusual values in the same
  order and reports `EA can't backtesting`; and
- a 2020 user discussion explicitly says a Life Changer build was renamed
  GOLDNIX and warns that it uses martingale. This is corroboration from users,
  not authoritative source documentation.
  [Life Changer/GOLDNIX discussion](https://www.forexforum.co/threads/anyone-have-settings-for-life-changer-ea.10007/page-3)

The video then loads the archived `M1 GOLD SET.set`; its inputs change exactly
to `Step=40`, `TakeProfit=15`, XAUUSD/GOLD, one active pair, comment
`MT4PRO.NET`, and no time filter. The Trade tab remains empty with balance,
equity and free margin all USD 116.54 and profit zero. None of the three videos
shows an entry, exit, account history or test result. The installation video
uses a different EA, and the phone video only demonstrates remote desktop.

The best description is therefore: **GOLDNIX is almost certainly a configured
or renamed build of the Life Changer / Profit Maker family.** This establishes
code lineage, not authorship, licensing, or a byte-identical match to any
public MQ4. The public code has generic/decompiler-style variable names and
different defaults in places; it is useful for reconstruction but is not an
authenticated original source release.

## What presets can and cannot reveal

MQL4 `input` variables are values exposed in a program's Properties window;
the user may change them, and MQL4 reinitializes them before `OnInit()`.
[MQL4 input variables](https://docs.mql4.com/basis/variables/inputvariables)
MetaTrader's Expert Properties also allows a previously saved set of inputs to
be loaded and the current set to be saved. The same page explains that test
values and optimization ranges are separate.
[Strategy Tester properties](https://www.metatrader4.com/en/trading-platform/help/overview/strategy_tester/strategy_tester_properties)

This means the `.set` files are strong evidence of GOLDNIX's public input
interface. They are weak evidence of the hidden implementation: a program may
use an input in a non-obvious way, conditionally ignore it, transform its units
or leave it unused. A name such as `Multiplier` is not source code.

The material differences among the four presets are below. The dollar-distance
columns use the recovered family's intended gold conversion: one input distance
unit equals 0.10 in XAU price. This holds for ordinary two-digit gold and exact
three-digit names `XAUUSD`/`GOLD`; a three-digit broker suffix can miss the
source's exact-name special case and make distances ten times tighter.

| Preset | `FixLot` | `Multiplier` | `Step` | Likely XAU step | `TakeProfit` | Likely XAU TP | `Stoploss` | Likely XAU SL |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `single layer entry m1 gold.set` | 0.01 | 1.00 | 1000 | $100.00 | 15 | $1.50 | 40 | $4.00 |
| `layer gila gold m1.set` | 0.01 | 1.00 | 5 | $0.50 | 15 | $1.50 | 400 | $40.00 |
| `layer santai gold m1.set` | 0.01 | 1.50 | 20 | $2.00 | 15 | $1.50 | 400 | $40.00 |
| `M1 GOLD SET.set` | 0.01 | 1.11 | 40 | $4.00 | 15 | $1.50 | 400 | $40.00 |

All four also set `MaxTrades_EachSide=50`, `MagicNumber=1234567`, enable a
trailing stop of 12 with step 1, name `XAUUSD` and `GOLD` as the first two
symbols, set `MaxPairTrades=1`, and disable the trading-time filter while
retaining `00:00` to `23:59`. The readme says to use GOLD/XAUUSD on M1 with a
setfile.

## Reconstructed trading logic

### First-entry signal: Aroon Oscillator (70)

The matching code declares a 70-bar lookback, threshold 50 and start shift 1.
For the most recent and previous closed-bar windows it calculates:

```text
AroonUp    = 100 * (70 - shift_of_highest_high + start_shift) / 70
AroonDown  = 100 * (70 - shift_of_lowest_low  + start_shift) / 70
oscillator = AroonUp - AroonDown
```

This is the standard idea of an Aroon Oscillator implemented directly with
`iHighest` and `iLowest`; no separate chart indicator is required. It then:

- opens BUY when the oscillator crosses from below +50 to above +50;
- opens SELL when it crosses from above -50 to below -50; and
- in this source variant, also requires current-bar tick volume below 30 for
  SELL, but not BUY.

The windows begin at shifts 1 and 2, so the price-extreme calculation uses
closed bars. The chart timeframe is used; with the supplied M1 instruction,
the signal therefore examines roughly the prior 70 minutes. An opposite signal
does not close an existing basket. The asymmetric SELL volume condition is
present in the matching public code, but remains one of the details that should
be confirmed against this exact encrypted build.
[Life Changer code preview and signal](https://mql-files.ru/product/life-changer-ea-1-mq4-4600)

### Adverse grid, geometric lots and recovery exit

After the first order, the family code:

- adds another BUY after Ask falls by `Step` from the latest BUY entry;
- adds another SELL after Bid rises by `Step` from the latest SELL entry;
- chooses later lots approximately as
  `FixLot * Multiplier^existing_layers`, rounded and clamped to the broker's
  minimum and maximum; and
- stops adding at `MaxTrades_EachSide` or when free margin is insufficient.

This is averaging into loss, not adding to a winning trend. A margin check is
not account protection: it only prevents the next order after exposure has
already accumulated.

The first order is submitted with the configured TP and SL. Later layers carry
the basket's existing stop and initially have no TP. Once more than one order
exists, the family code estimates aggregate break-even from basket P/L, total
lots and tick value, then moves all targets to a small profit beyond break-even
(five internal distance units in the public variant). Trailing logic is applied
when only one position exists. The time filter gates new first entries, while
layer and exit management continue outside that window.

The source assigns the same magic number to BUY and SELL management. In that
variant any existing order blocks a new opposite first order, so it runs one
directional basket per symbol rather than simultaneous hedging. `MaxPairTrades`
limits how many configured symbols may have a basket open at once.

### Confidence summary

| Finding | Confidence | Basis |
| --- | --- | --- |
| GOLDNIX is a Life Changer / Profit Maker family rebrand or configured build. | Very high | Internal metadata, exact chart slogan, matching dashboard/default inputs, public code, contemporary user report. |
| First entry uses an Aroon Oscillator(70) crossing +/-50. | High for lineage; medium-high for this exact EX4 | Matching identity and code path; encrypted payload prevents byte-level comparison. |
| It averages adversely at fixed `Step` intervals. | High for lineage; medium-high for this exact EX4 | Explicit matching order logic plus four purpose-named presets. |
| Lots grow geometrically when `Multiplier > 1`. | High for lineage; medium-high for this exact EX4 | Explicit lot function and exact exposed multiplier. |
| Multi-layer exits use a shared recovery target near basket break-even. | High for lineage; medium for hidden constants in this EX4 | Explicit matching basket logic; target offset is not exposed in GOLDNIX presets. |
| It is AI, uses news/fundamentals, or learns from trades. | Contradicted by recovered logic | Deterministic price-extreme and order-management rules; no model or training path found. |
| It is profitable, wins above 50%, or averages USD 20 weekly. | Unsupported | No authenticated report, trade ledger or reproducible test is supplied. |

### Preset exposure implications

Assuming the matching family logic and ordinary gold price scaling, the stop
on later layers remains anchored to the first basket stop. Ignoring spread,
slippage, broker lot caps and margin failure, and applying source-style
two-decimal lot rounding:

| Preset | Layers strictly before original SL | Approximate cumulative lots |
| --- | ---: | ---: |
| `single layer entry m1 gold.set` | 1 | 0.01 |
| `layer gila gold m1.set` | 50-order cap | 0.50 |
| `layer santai gold m1.set` | about 20 | about 107.76 |
| `M1 GOLD SET.set` | about 10 | about 0.17 |

For the 1.50 and 1.11 presets, the next grid threshold would coincide with the
original $40 stop after approximately 20 and 10 open orders respectively; tick
ordering and slippage can change the boundary case. The `single layer` name is
internally consistent: its next layer is $100 away, but its SL is only $4 away.
Conversely, `layer gila` can fill all 50 fixed-lot orders within a $24.50
adverse move while the original stop is about $40 away. The 1.5 multiplier in
`layer santai` is exponential; a real account would normally hit broker lot
limits, insufficient margin or stop-out long before the mathematical sequence
completed. Those interventions are failure modes, not safety mechanisms.

Absence of a companion indicator does not prove that no indicator is used.
MetaQuotes documents that resources, including compiled custom indicators, can
be embedded in an EX4. MQL4 programs may also import functions from DLLs or
other EX4 libraries.
[MQL4 resources](https://docs.mql4.com/runtime/resources),
[external functions](https://docs.mql4.com/basis/function/extfunctions)

## Safe black-box test contract

MetaTrader 4's Strategy Tester evaluates an EA on historical quotes and makes
virtual transactions rather than real trades. It supports visual testing and
produces transaction, profit/loss, win/loss and risk information.
[MetaTrader 4 Strategy Tester](https://www.metatrader4.com/en/automated-trading/strategy-tester)
This makes it the appropriate dynamic-observation tool, but executing an
unknown binary still needs containment.

Before the first run:

1. Use a disposable Windows VM with a snapshot, no personal files, no saved
   broker or email credentials and no live account login. Keep the host copy of
   the archive read-only and verify the EX4 hash after transfer.
2. Keep terminal-wide AutoTrading disabled and never attach the EA to a normal
   chart. MetaQuotes says disabling AutoTrading prevents EAs from performing
   trade operations, and also provides a per-program permission.
   [MQL4 trade permission](https://docs.mql4.com/runtime/tradepermission)
3. Before loading the EA, disable DLL imports and leave the WebRequest allowlist
   empty. MetaQuotes labels DLL imports potentially dangerous and recommends
   disabling them for unknown experts; WebRequest is disabled by default and
   requires trusted URLs to be listed. Its warning also says these defaults do
   not retroactively change already-running programs.
   [Expert Advisor terminal settings](https://www.metatrader4.com/en/trading-platform/help/setup/setup_experts)
4. Prefer a network-blocked VM after obtaining the required terminal and test
   history. Treat any request for a DLL, URL, activation key or external EX4 as
   a stop condition to investigate, not a reason to weaken containment.
5. Record the MT4 terminal build, broker-history source, symbol specifications,
   date range, timeframe, modeling mode, spread, starting balance, leverage,
   preset hash and EX4 hash for every run.

Strategy Tester blocks `WebRequest`, email, FTP, notifications and several
other outside-world functions, and it only performs trade operations on the
symbol under test. It processes `OnInit`, `OnTick`, `OnTester` and `OnDeinit`,
but does not process Timer or ChartEvent events.
[MQL4 Strategy Tester limitations](https://docs.mql4.com/runtime/testing)
Therefore a quiet or incomplete test is not proof that the EA has no other
behavior: it could rely on an unsupported event, another symbol, an external
component or a condition absent from the sample.

There is also a family-specific obstacle: the exact 2019 input-compatible
build logged `EA can't backtesting` and stopped during initialization. Trial
and tester guards exist in recovered Life Changer variants, although some
copies comment them out. If this EX4 exits with that message, record the result;
do not patch or bypass the guard and then describe the modified program as the
original. The fallback is forward observation in a disposable VM on a new demo
account with no real funds or reused credentials.

### Binary-validation runs

Use a fixed historical interval first and change one input at a time. Do not
optimize for profit during this phase.

1. Run `single layer entry` with `MaxTrades_EachSide=1`. Export Results, Report
   and Journal. Compare every first order with an independently calculated
   Aroon(70) +/-50 crossing on closed bars.
2. Check whether SELL entries occur only while current-bar tick volume is below
   30 and whether BUY lacks that restriction.
3. Repeat with the maximum at 2 and 3. Vary `Step` widely and measure the exact
   adverse entry-to-entry distance in both directions.
4. Compare `Multiplier=1`, `1.11`, `1.5` and `2` with the same three-layer cap.
   Record the precise lot sequence and broker rounding.
5. Disable trailing, then vary take-profit and stop-loss individually. Confirm
   initial ticket TP/SL, inherited basket stop, common break-even recovery TP,
   and single-order trailing behavior.
6. Enable a narrow trading-time window and verify that it gates the first
   order but not recovery layers or exits.
7. Attempt an opposite Aroon crossing while a basket is open and check whether
   the EA remains one-directional.
8. Repeat frozen cases on two- and three-decimal gold names, including a symbol
   suffix, because the recovered source uses exact string comparisons for its
   three-digit gold conversion.

The Results tab records operation time, type, ticket, lot size, price, stop,
target, profit and balance; the Journal records tester messages and operations.
The Report includes modeled bars/ticks, net profit, drawdown, trade count and
win/loss statistics.
[Tester results](https://www.metatrader4.com/en/trading-platform/help/overview/strategy_tester/strategy_tester_results),
[Tester journal](https://www.metatrader4.com/en/trading-platform/help/overview/strategy_tester/strategy_tester_journal),
[Tester report](https://www.metatrader4.com/en/trading-platform/help/overview/strategy_tester/strategy_tester_report)

### Performance runs

Only after the behavior is understood should a preset be assessed for
performance. Freeze it before an untouched chronological test, include adverse
periods, preserve the full reports and distinguish repeated calculation from
independent evidence. Re-running the same binary, settings and history should
give the same result; that demonstrates determinism, not multiple independent
tests or future profitability.

MT4's tester models intra-bar price movement from bar history. MetaQuotes warns
that bar-only testing can be inaccurate, describes `Control points` as a crude
estimate, and recommends every-tick modeling with complete lower-timeframe
coverage for close testing. It also states that stored history contains Bid
prices and that, by default, the tester models Ask from the symbol's current
spread unless a custom spread is specified.
[Strategy Tester setup and modeling](https://www.metatrader4.com/en/trading-platform/help/autotrading/tester/tester_parameters)
For a step-based M1 system, report modeling quality and test several realistic
spreads; a single favorable spread or modeled-tick backtest cannot prove live
execution quality.

Optimization is not validation. MetaTrader can run many passes over the same
data and rank input combinations by profit, drawdown and other criteria, but a
best in-sample pass must be frozen and evaluated on later untouched data.
[Optimization results](https://www.metatrader4.com/en/trading-platform/help/overview/strategy_tester/strategy_tester_opt_results)

## Current blocker

The archive's exact original MQ4 is absent, the compiled payload is protected,
and the public source-family copy is not authenticated as byte-identical. This
investigation deliberately did not execute the unknown EX4; the current Mac has
no contained MT4/Windows runtime. Consequently the precise hidden constants,
the SELL tick-volume condition, suffix behavior, basket-target offset and
anti-tester state remain binary-validation questions.

The technique itself is no longer an unknown: the combined evidence supports
**Aroon(70) trend entry followed by adverse grid/martingale recovery** with high
confidence. What remains wholly unproven is performance. No supplied video or
file demonstrates one completed trade, a win rate above 50%, or average weekly
profit of any amount.
