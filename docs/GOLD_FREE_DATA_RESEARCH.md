# Credential-free XAU/USD data-source research

Checked against first-party Dukascopy, FXCM and AlgoSpecial pages, current
first-party client/documentation source, and bounded endpoint responses on
2026-11-07. This note distinguishes a personal historical export, a supported
research API, and a broker execution feed. No performance result or order was
produced by this research.

## Dukascopy verdict

Dukascopy has genuine XAU/USD spot-gold/CFD bid and ask history, and its
Historical Data Export page says that exports are free and range from ticks to
monthly data. The instrument is `XAU/USD` (`XAU-USD` in the current web-data
service), not a gold future or tokenized-gold pair. This makes a bounded export
technically suitable for personal historical research.
[Dukascopy Historical Data Export](https://www.dukascopy.com/swiss/english/marketwatch/historical/),
[Dukascopy gold product](https://www.dukascopy.com/swiss/english/cfd/range-of-markets/gold/)

It is **not** a safe zero-credential unattended backend. Dukascopy's website
terms allow downloaded material only for the user's personal, non-commercial
use, prohibit constructing a database, and prohibit bots, scrapers, data-mining
code or other automated acquisition without prior express written consent.
Dukascopy's separately documented programmable archive is an AWS S3
Requester-Pays bucket: it needs AWS credentials and incurs request and transfer
charges. Therefore neither route meets all three requested properties of free,
credential-free and unattended automation.
[Dukascopy Terms of Use](https://www.dukascopy.com/swiss/english/legal-pages/terms-of-use/),
[official S3 data-export guide](https://www.dukascopy.com/wiki/en/development/data-export/)

Do not integrate the undocumented web endpoints into a scheduled collector
unless Dukascopy gives express permission. A one-time export initiated through
the visible export tool may be used for this user's personal research under the
published terms, but its data must not be committed, redistributed, published,
or exposed through the public backend.

## Instrument identity

Dukascopy describes XAU/USD as a rolling spot-metal CFD whose price is based on
interbank loco-London XAU/USD, and distinguishes it from exchange-traded gold
futures. The minimum JForex trade size stated by Dukascopy is one troy ounce.
The current first-party instrument response identifies:

- name `XAU/USD`, service code `XAU-USD`;
- group `FX_METALS`, description `Gold vs US Dollar`;
- `pipValue: 0.01`, `priceScale: 3`, `contractSize: 1`;
- default session timezone `America/New_York`;
- tick and minute history beginning 2003-05-05 UTC, hourly history beginning
  the same day, and daily history beginning 1999-06-03 UTC.

The current response can be inspected at the first-party
[`XAU-USD` instrument resource](https://jetta.dukascopy.com/v1/instruments/XAU-USD).
The history start values are provider metadata, not a guarantee that every
interval is present or error-free.

Gold has a daily trading break and special holiday closures, so the generic
24/5 forex calendar in the repository is insufficient. Dukascopy currently
publishes a one-hour XAU/USD break at 21:00-22:00 GMT in summer and 22:00-23:00
GMT in winter, plus a longer US-holiday break. The instrument resource also
returns dated schedules and holidays; a collector must snapshot and validate
them instead of hard-coding today's schedule forever.
[Dukascopy trading hours](https://www.dukascopy.com/europe/english/forex/forex_trading_accounts/link/)

## Data contract observed in the first-party export client

The current Historical Data Export client loads its data-service origin from
[`config.json`](https://widgets.dukascopy.com/config.json) and uses Dukascopy's
Jetta service. Its first-party client source exposes separate history paths for
ticks, one-minute, hourly and daily candles. This is evidence of current widget
behaviour, **not a stable or licensed public-API promise**.
[export widget](https://widgets.dukascopy.com/en/historical-data-export),
[current first-party history client source](https://widgets.dukascopy.com/en/chunk-BKWyMYyg.js)

The current decoded contracts are:

- minute candle response: base `timestamp`, numeric `multiplier`, base OHLC,
  fixed `shift`, delta arrays `times`, `opens`, `highs`, `lows`, `closes`, and
  `volumes`;
- tick response: base `timestamp`, `multiplier`, base `bid` and `ask`, plus
  delta arrays `times`, `bids`, `asks`, `bidVolumes`, and `askVolumes`;
- offer side: minute history is requested separately as `BID` or `ASK`; tick
  history contains both sides;
- timestamps: epoch milliseconds decoded in UTC, with display/export conversion
  to the selected timezone;
- export output: timestamp, OHLC and volume, with selectable bid or ask side.

A bounded direct check of 2026-11-06 returned 1,320 one-minute XAU/USD rows for
each of BID and ASK. Tick files for 20:00 and 21:00 UTC returned 17,332 and
10,317 ticks respectively, while 22:00 returned no ticks after the Friday
close. These counts demonstrate endpoint/data shape only; they are not a
quality certification or a performance result.

The export page describes the available values as bid/ask prices and trading
volumes. It does not establish that volume is centralized exchange notional;
gold CFD/spot volume must therefore be treated as provider activity/liquidity
metadata, not physical-gold or exchange volume.
[export field description](https://www.dukascopy.com/api/data/get/historical-data-export)

## Recency and live-use limit

The current web client contains a polling method that requests successive
10-second tick windows, and the public gold page advertises real-time spot-gold
quotes through Dukascopy's platforms. That shows a recent-data path exists, but
the export service provides no public uptime, latency, entitlement or
executable-price guarantee. A web quote is not a broker order acknowledgement
or fill.
[current first-party history client source](https://widgets.dukascopy.com/en/chunk-BKWyMYyg.js),
[Dukascopy gold product](https://www.dukascopy.com/swiss/english/cfd/range-of-markets/gold/)

Consequently, a local simulated fill using this feed could only demonstrate
the simulator's accounting under declared assumptions. It could not prove a
Dukascopy paper fill, OANDA Practice fill, or future profitability.

## Access, rate and cost constraints

The visible Historical Data Export is free and Dukascopy's general website
terms say website access does not require being a client. No documented request
quota or service-level agreement is published for the widget's internal Jetta
routes. During this check, plain command-line requests received an AWS WAF
challenge; requests matching the visible widget origin succeeded. This is an
additional sign that the routes are implementation details rather than a
supported general-purpose API. Headers must never be forged to evade access
controls.

The supported bulk/programmatic route described in Dukascopy's official guide
uses `s3://cfg-public-proper-wallaby` in `eu-west-1` with AWS Requester Pays.
The guide requires valid AWS credentials and explicitly estimates request and
egress costs. It also warns that non-FX point scaling, including XAU/USD, must
be confirmed rather than inferred from ordinary currency pairs. It therefore
does not satisfy a strict zero-cost/no-credential requirement even though the
underlying archive is public.
[official S3 data-export guide](https://www.dukascopy.com/wiki/en/development/data-export/)

## Alternatives that are not equivalent

- COMEX gold futures such as `GC` have expiry/roll behaviour and exchange
  contract specifications; they are not XAU/USD rolling spot.
- PAXG, XAUT or other tokenized-gold crypto pairs have issuer, custody, venue
  and market-structure risks; they are not XAU/USD.
- A midpoint-only series cannot measure the executable bid/ask spread and is
  inadequate for an after-cost claim.

Substituting any of these without changing the research question would make the
result misleading.

## FXCM public MarketData candidate

FXCM's MarketData repository is first-party: GitHub marks the `fxcm`
organization as verified for `fxcm.com`. The repository publishes a public
candle-file convention and official Python download examples, so automated
personal downloads of the specifically listed archive are an intended use,
subject to FXCM's EULA. It is a materially clearer automation signal than
reverse-engineering an internal web-widget endpoint.
[verified FXCM organization](https://github.com/FXCM),
[FXCM MarketData repository](https://github.com/fxcm/MarketData),
[official candle downloader](https://github.com/fxcm/MarketData/blob/master/CandleData/CandleData%28pandas%29.py)

The public candle contract is:

```text
https://candledata.fxcorporate.com/{periodicity}/{instrument}/{ISO year}/{ISO week}.csv.gz
```

It offers `m1`, `H1`, and `D1`; the official sample code uses Python's
`date.isocalendar()` for the ISO week and ISO week-year. FXCM says m1 and H1
files are compiled by trading week and updated every Monday, timestamps are
UTC, and the points are indicative prices based on the lowest spreads available
to Active Trader accounts. A bounded check of a documented EUR/USD file
confirmed this schema:

```text
DateTime,BidOpen,BidHigh,BidLow,BidClose,AskOpen,AskHigh,AskLow,AskClose
```

There is no volume field. Separate bid and ask OHLC would be useful for
after-spread historical simulation, but they are indicative and cannot certify
an executable fill.
[FXCM candle-data specification](https://github.com/fxcm/MarketData/blob/master/CandleData/README.md),
[FXCM market-data explanation](https://www.fxcm.com/pro/market-data/fx-price-feed/)

**XAU/USD is not in that public candle archive's documented instrument list.**
The list contains ordinary currency pairs only. Representative no-credential
checks for `XAUUSD` returned HTTP 404 for m1, H1, and D1 files across old and
recent years; `XAU-USD`, `XAU_USD`, and URL-encoded `XAU/USD` did not reveal a
public candle path either. In contrast, a documented EUR/USD weekly file
returned data, confirming that the host itself was working during the check.

FXCM does list `XAU/USD` as an instrument in its ForexConnect API metadata, with
minute and hourly history beginning in 2009. That establishes that FXCM has
gold data, not that the data is present in the free public candle archive.
ForexConnect is an account/API product. Likewise, the MarketData root README
lists `XAUUSD` only for one-month sentiment and volume samples; neither contains
gold OHLC prices and neither can drive this strategy.
[FXCM API symbol coverage](https://github.com/fxcm/ForexConnectAPI/blob/master/AvailableSymbols.md),
[FXCM MarketData root README](https://github.com/fxcm/MarketData)

The repository's current TickData documentation tells users to request access
by email, and the tick-data host redirects unauthenticated requests to
Cloudflare Access. It therefore does not provide a no-auth XAU/USD fallback.
[FXCM TickData README](https://github.com/fxcm/MarketData/blob/master/TickData/README.md)

FXCM labels the public files as free for personal use under its EULA. Its EULA
page currently requires an application/form rather than exposing complete
license text, so no broader redistribution or service-use right should be
inferred. Raw files must remain private and cannot be treated as an
open-license dataset.
[FXCM Software EULA page](https://www.fxcm.com/uk/forms/eula/)

**Conclusion:** FXCM's public archive would be suitable for two independent
chronological tests of one of its documented currency pairs, using
non-overlapping ISO-week files. It cannot support the requested XAU/USD tests
because public gold price files were neither documented nor present. FXCM
account/API credentials or a commercial arrangement would still be needed for
gold and for any broker-paper execution.

## AlgoSpecial verdict: bounded historical research only

**Verdict: usable with material caveats for private, bounded XAU/USD historical
research; not acceptable as broker execution evidence or as proof of a future
win rate.** AlgoSpecial publishes a keyless HTTP API, Python and cURL examples,
chunking/retry guidance, and an explicit statement that the API is free for
research, backtesting and commercial applications. It prohibits reselling or
redistributing the API as a standalone data service and tells users to verify
the data against their broker. These are clear signals that normal automated
research requests are intended, unlike the undocumented Dukascopy widget
routes.
[AlgoSpecial API overview](https://www.algospecial.com/data-api/),
[Python API guide](https://www.algospecial.com/data-api/python/)

The permission is not an open-data licence. Keep cached responses private and
do not republish a reconstructed raw-data service. The Python guide expressly
recommends caching successful raw responses, so private local retention for a
research workflow is contemplated. No duration, archive-retention guarantee,
revision policy, immutable dataset version, change log, or service-level
commitment was found. Record the retrieval time, request parameters, response
headers, coverage and cryptographic hashes; a later response must not silently
replace a frozen test set. The site's generic terms add trading-risk and
no-profit-guarantee disclaimers but do not identify a separate upstream market
data licence.
[AlgoSpecial terms](https://www.algospecial.com/terms.php)

### Provenance and instrument limitations

The M15 catalog reports 225,077 `XAUUSD` bars from 2017-01-19 through
2026-10-30. It calls this an "Exness-style source feed" quoted to three decimal
places. That wording does **not** identify Exness, a legal data vendor, a broker
server, account type, liquidity source, venue, symbol specification or quote
side. Neither the quality endpoint nor the observed response headers supplied
an upstream source identifier. The series therefore cannot be represented as
Exness data, OANDA data, consolidated spot gold, or an executable price from
the user's broker.
[AlgoSpecial XAU/USD guide](https://www.algospecial.com/data-api/xauusd/)

The response has one OHLC series, `TickVolume`, and one integer `Spread` per
bar. The documentation does not say whether OHLC is bid, ask, midpoint or
another broker price. `TickVolume` is a tick count where supplied, not ounces,
notional turnover or centralized exchange volume. There are no bid/ask OHLC
paths, depth, trade prints, financing, commission, swap, liquidity, order
acknowledgements or fills. Consequently, the feed can support bar-level price
research but not exact stop/limit execution simulation or a claim that a broker
would have filled a trade.

### Timestamp ambiguity

AlgoSpecial labels timestamps as broker server time and explicitly says they
are not UTC, but publishes no broker name, IANA timezone, UTC offset history,
daylight-saving rule or server-change calendar. Its instruction to "convert to
UTC" is not reproducible without that missing mapping.

A bounded October 2026 sample had the ordinary daily break between the
20:45 and 22:00 labels, while a bounded January 2026 sample placed it between
21:45 and 23:00. That seasonal change is consistent with more than one possible
clock/session convention; it does not establish which convention the stored
labels use. It does show that a fixed offset or hard-coded clock boundary is
unsafe. Preserve the source string as provider-local time. Until AlgoSpecial
publishes the mapping, do not label it UTC and do not use London/New York/Asia
session features. Price-only chronological ordering remains possible, provided
gap bars and trades spanning closures are excluded.

### Spread units and execution-cost limit

AlgoSpecial defines `Spread` as broker points and says this XAU/USD feed uses
three decimal prices. On that documented scale, one point is 0.001 in quoted
price, conventionally USD 0.001 per troy ounce for XAU/USD: for example,
`Spread: 240` represents USD 0.240, not USD 240 and not 240 pips. A bounded
2024-01-02--2024-01-03 sample varied from 199 to 600 points. In contrast, all
1,288 bars in the bounded 2026-10-01--2026-10-20 sample reported exactly 240
points. That constant recent value is not evidence of a continuously observed
historical bid/ask spread.

Any test must therefore state that its cost model is an approximation. Apply at
least the reported spread where nonzero, replace zero/missing values with a
predeclared conservative value, add a slippage stress, and report sensitivity
to wider costs. Do not infer an ask candle by mechanically shifting every OHLC
field, and do not call the result an executable after-cost broker test.
[AlgoSpecial CSV/JSON field guide](https://www.algospecial.com/data-api/csv-json/)

### Live response limits conflict with some documentation

The current overview and live endpoint enforce a free-preview limit of 2,000
rows and 31 calendar days per request. A request for
2026-10-01--2026-10-31 returned HTTP 413 with `max_rows: 2000`; a request for
2026-01-01--2026-12-31 returned HTTP 400 with the 31-day explanation. A
successful response exposed minute-limit headers with a limit of 60. The
overview also publishes 1,000 requests per day.

Other current AlgoSpecial pages still claim 50,000 rows and 366 days, and their
examples recommend monthly, quarterly or yearly chunks. Those claims conflict
with the overview and actual enforcement. A client must obey the stricter live
contract, bound each request below both caps, cache it, stop on 400/413, and
respect `Retry-After` on 429. The site's simultaneous use of "free preview,"
paid full-history downloads, and multi-year chunking examples also leaves the
intended scope of reconstructing the entire catalog ambiguous. A small number
of preregistered research windows is supportable under the express backtesting
permission; bulk reconstruction of all history should be confirmed with the
provider or bought rather than inferred.
[AlgoSpecial rate-limit page](https://www.algospecial.com/data-api/rate-limits/)

### Published quality warnings

The provider's generated M15 report gives the file 97/100 (grade A), but this is
a structural score rather than independent price verification. The same report
records:

- 2,942 gaps greater than two M15 intervals and under 24 hours, with a largest
  gap of nine hours;
- 1,364 zero or missing spread values (0.61%);
- 19 flat bars;
- six bars classified as invalid weekend bars;
- no duplicate or out-of-order timestamps, OHLC integrity violations,
  nonpositive prices, negative spreads, or reported extreme returns.

Expected daily/holiday closures account for some gaps, but the report does not
classify every gap by exchange/broker schedule. Gap and weekend records must be
investigated or excluded before labels are generated. The report itself warns
that a high score does not guarantee a profitable backtest.
[XAU/USD M15 quality report](https://www.algospecial.com/historical-data/data-quality/xauusd-m15/)

### Small independent-source sanity check

One bounded AlgoSpecial request for 2024-01-02--2024-01-03 returned 184 M15
bars. Its first provider-local 00:00 bar opened at USD 2,063.608. The
already-recorded bounded Dukascopy sample opened its 00:00 UTC first minute at
USD 2,063.625 bid and USD 2,063.996 ask. The AlgoSpecial value was therefore
USD 0.017 from the Dukascopy bid open and within the contemporaneous quote
scale.

This is only a plausibility check. The aggregation differs (M15 versus the
first M1 bar), AlgoSpecial's clock zone and OHLC side are unspecified, and
Dukascopy is a separate broker feed. The match cannot prove common provenance,
bar-for-bar correctness, spread correctness, or executable equivalence. No
clean public source with both an allowed automated historical archive and the
same recent interval was found for a broader no-credential comparison.

### Can it support two chronological historical tests?

It can support **two bounded, disjoint, locked historical evaluations** if the
following contract is fixed before either result is inspected:

1. Predeclare the development period, both test windows, purge/embargo, one-hour
   horizon, model and thresholds, cost/slippage policy, and all pass/fail gates.
2. Freeze the model before Test A and make no selection or tuning change after
   viewing Test A or before Test B. Otherwise Test A becomes development data
   and only Test B remains an untouched holdout.
3. Use private cached responses with hashes; de-duplicate inclusive chunk
   boundaries and require identical overlapping boundary bars.
4. Disable session/time-of-day features unless the timestamp mapping is
   independently established. Exclude labels and trades that cross a missing
   interval, daily break, weekend or holiday closure.
5. Report closed wins and losses, after-cost win rate with a predeclared 95%
   confidence interval, net return, profit factor, drawdown, Sharpe, trade
   count and simple benchmarks. A point estimate above 50% is not proof; an
   underpowered result is inconclusive.

The two windows are not independent market replications: they come from one
opaque provider and one already-known historical record. They also do not meet
the stronger [double-test contract](GOLD_RESEARCH.md), whose second test is
fresh OANDA Practice quotes and transactions after the model is frozen.
AlgoSpecial ends on 2026-10-30 and exposes no live quote, order or fill API, so
it cannot produce that forward test or a genuine paper trade.

## Safe next options

1. For a no-key preliminary result, use only bounded, preregistered
   AlgoSpecial historical windows under the caveats above. Keep raw responses
   private, hash them, and label the outcome research-only.
2. Use the visible Dukascopy export manually for a separate bounded, private
   price sanity check; keep raw data out of Git and public APIs.
3. Obtain written permission or pay for a supported source when broader
   historical coverage is required.
4. Supply a Practice broker credential whose terms permit automated quotes and
   paper execution for the required untouched forward test.

AlgoSpecial is the clearest genuinely keyless automated XAU/USD research option
found, but its opaque source, unknown clock mapping, undefined OHLC side,
approximate spread history and lack of execution endpoints cap the conclusion.
It can produce historical research evidence, not an immediate honest broker
paper trade and not proof that a strategy will win more than 50% in the future.
