# Gold weekly-target method: primary-source research and locked recommendation

Research completed on 2026-11-07. This document selects a different strategy
family for a new historical test. It does not claim that USD 20 can be earned
every week and does not authorize a broker order.

## Bottom line

The best defensible next candidate is **medium-horizon time-series momentum
(trend following), volatility-scaled and capped at 1x notional exposure**. It is
materially different from the failed M15 LightGBM probability-threshold test:
there is no classifier, probability threshold, intraday session feature, or
parameter search.

The candidate can honestly test whether a USD 10,000 paper account produced
more than USD 20 **on average per seven-day block** in two untouched historical
periods. It cannot promise USD 20 in every future week. USD 20 on USD 10,000 is
0.20% per week, 10.4% by simple annualisation, or about 10.95% compounded over
52 identical positive weeks. Reaching that return by increasing leverage after
seeing results would invalidate the test.

The CFTC says no person or program can guarantee future results and warns that
leverage magnifies losses; its OTC advisory also reports that most retail forex
customers lost money after financing, fees and other expenses. Those warnings
make “guaranteed USD 20 every week” an invalid pass condition, not a strategy
feature.
[CFTC no-guarantee advisory](https://www.cftc.gov/sites/default/files/2020-03/20200312_CustomerAdvisory_Corona_FINAL.pdf),
[CFTC OTC forex advisory](https://www.cftc.gov/LearnAndProtect/AdvisoriesAndArticles/CustomerAdvisory_MustKnowForex.html)

## Why this family, and what the evidence does not say

Moskowitz, Ooi and Pedersen documented positive predictability from an
instrument's own past returns across 58 liquid futures and forwards, including
commodities, with persistence over roughly one to twelve months. Their result
is portfolio-level and futures/forward evidence; it does not prove that one
retail XAU/USD CFD will be profitable after its broker-specific costs.
[Time Series Momentum, Journal of Financial Economics](https://fairmodel.econ.yale.edu/ec439/mosk.pdf),
[original paper data](https://www.aqr.com/Insights/Datasets/Time-Series-Momentum-Original-Paper-Data)

Hurst, Ooi and Pedersen extended trend-following evidence across a much longer
history. Their documented construction combines binary 1-, 3- and 12-month
time-series momentum signals, rebalances monthly, sizes markets by volatility,
and targets 10% annualised portfolio volatility. The authors explicitly frame
the work as historical analysis rather than a product recommendation or an
assurance of future returns.
[A Century of Evidence on Trend-Following Investing](https://www.aqr.com/Insights/Research/Journal-Article/A-Century-of-Evidence-on-Trend-Following-Investing),
[documented 1/3/12-month construction](https://www.aqr.com/-/media/AQR/Documents/Journal-Articles/JPM-You-Cant-Always-Trend-When-You-Want.pdf?sc_lang=en)

Szakmary, Shen and Sharma found positive net mean excess returns for many dual
moving-average and channel rules across a broad commodity-futures panel. This
supports trend following as a family but not choosing whichever gold rule looks
best after viewing the requested holdouts. To avoid that multiple-testing trap,
the next run should test one predeclared 1/3/12-month construction only.
[commodity trend-following study](https://doi.org/10.1016/j.jbankfin.2009.08.004)

Volatility management has evidence in other factor portfolios, but it cannot
create expected return by itself. Its role here is risk normalisation: reduce
the position when measured volatility is high and enforce a hard exposure cap.
[Moreira and Muir, Volatility Managed Portfolios](https://www.nber.org/papers/w22208)

## Locked candidate specification

The following is frozen before any response in the new test window is downloaded.

### Account and observations

- Initial paper equity: USD 10,000.
- Instrument: research feed symbol `XAUUSD`; one unit is treated as one troy
  ounce only for the historical arithmetic.
- Inputs: provider-local M15 OHLC, tick volume and spread. Timestamps remain
  unknown broker-server time, never UTC.
- Decision frequency: the final complete bar of each provider-calendar month.
  Month labels are source-clock labels, not London, New York or UTC sessions.
- Execution: calculate with information available at the completed month-end
  bar and change the position only at the next available bar open.
- No clock/session, news, volume, AI or macroeconomic features.

### Direction signal

At each rebalance, calculate price returns from the current completed
provider-month close to the completed closes 1, 3 and 12 provider months ago.
Map each strictly positive return to +1 and each non-positive return to -1.
The trend score is their arithmetic mean, so it is one of -1, -1/3, +1/3 or
+1. This is fixed before the data is read; there is no validation search.

### Volatility and position size

- Estimate annualised volatility from the previous 12 completed
  provider-month returns only, with sample standard deviation and `sqrt(12)`.
- Raw exposure multiplier: `0.10 / estimated_annualised_volatility`.
- Final signed notional:
  `trend_score * min(1.0, raw_multiplier) * USD 10,000`.
- Convert notional to ounces using the next-bar open. Round down to the
  account-returned unit precision when a real Practice account exists; for this
  source-only test retain six decimals and report that this is not proof the
  broker accepts that size.
- Absolute notional is capped at USD 10,000. No leverage above 1x, martingale,
  averaging down, pyramiding or post-result rescaling is permitted.
- Rebalance once per provider month. A sign change closes the old side and
  opens the new side at the same next-bar event with separate costs.

This adapts the published multi-market 10% volatility target to one instrument
but deliberately removes the portfolio diversification benefit. It should be
described as an adaptation, not a reproduction of the academic portfolio.

### Price, transaction and carrying costs

AlgoSpecial defines timestamps as broker-server time and may report zero when
legacy spread data is unavailable. It does not identify the upstream broker,
quote side or executable fill. Raw data therefore stays private, gaps are not
interpolated, and this remains source-only research.
[AlgoSpecial field specification](https://www.algospecial.com/data-api/csv-json/),
[AlgoSpecial XAU/USD guide](https://www.algospecial.com/data-api/xauusd/)

For every position change:

- buy at next open plus one full reported spread and 2 bps slippage;
- sell at next open minus one full reported spread and 2 bps slippage;
- charge an additional 1 bp commission per side;
- replace a missing/zero spread with the 99th percentile of nonzero spreads
  from the December 2020--December 2021 warm-up period, frozen before either
  test;
- value weekly open positions at conservative immediate-liquidation prices.

The monthly strategy necessarily holds overnight. OANDA says gold financing
is applied to positions open at 5pm ET, long and short rates can differ and
change daily, and weekend financing is commonly tripled. Exact historical
account rates are unavailable from the anonymous source.
[OANDA Singapore financing rules](https://www.oanda.com/sg-en/trading/financing-costs/)

Therefore the source-only test must not invent “actual OANDA financing.” Apply
an explicitly synthetic debit to **both** long and short absolute notional for
every elapsed day held:

- primary stress: 10% annualised, `abs(notional) * 0.10 * days / 365`;
- sensitivity: 5% and 15% annualised;
- a pass must survive the 10% primary stress; report, but do not optimise to,
  the two sensitivities.

When credentials eventually exist, replace the stress with the account's
returned instrument financing, commission, precision, margin and size rules.
Those fields are account-specific in OANDA's schema.
[OANDA instrument schema](https://developer.oanda.com/rest-live-v20/primitives-df/)

## Locked unseen periods

Use only the provider interval 2020-12-01 through 2023-12-31. The source's
current free-preview endpoint limits requests to 31 days and describes complete
history downloads as paid. This bounded D1-only window needs about 37 small
requests and avoids reconstructing the seven-year intraday archive. No request
for this window had been made when this specification was revised.

- December 2020 through December 2021: warm-up for the 12-month momentum and
  volatility calculations and the zero-spread fallback; no pass/fail result.
- Test A: 2022-01-01 through 2022-12-31 provider time.
- Test B: 2023-01-01 through 2023-12-31 provider time.
- Capital resets to USD 10,000 and the strategy is forced flat at the boundary;
  no position, P/L or financing carries from Test A into Test B.

The code, costs, signal and position rules must be frozen before Test A is
inspected, and nothing may change between A and B. Both tests use the same
opaque provider, so they are chronological holdouts, not independent data-source
replications and not broker-forward evidence.

## Exact USD 20 pass/fail contract

Partition each test into consecutive non-overlapping seven-day blocks anchored
at that test's provider-time start. Weekly P/L is the change in conservative
marked equity after every spread, slippage, commission and financing debit.
An incomplete final block is reported but excluded from the mean.

Each test must independently satisfy every gate under the 10% financing stress:

1. at least 52 complete seven-day blocks;
2. arithmetic mean weekly net P/L greater than USD 20;
3. a one-sided 95% circular block-bootstrap lower confidence bound for mean
   weekly net P/L greater than USD 20, using 10,000 resamples, seed 42 and
   block length `max(2, floor(sqrt(complete_weeks)))`;
4. positive total after-cost P/L and profit factor above 1.0;
5. maximum marked-equity drawdown no worse than -10%;
6. positive provider-week Sharpe and positive median weekly P/L;
7. no margin or 1x-notional-cap breach; and
8. after-cost return above both cash and a 1x-notional buy-and-hold benchmark
   (`USD 10,000 / entry price` ounces) evaluated with the same transaction and
   financing stresses over the same interval.

Also report the number and percentage of weeks above USD 20, profitable weeks,
median, 5th percentile and worst weekly P/L. Do **not** require every week to be
profitable: a strategy with positive expectation still has losing observations.
Do not pool A and B, stop early, change exposure to hit the dollar target, or
select a different rule after seeing either holdout. A point mean over USD 20
whose confidence bound does not exceed USD 20 is **inconclusive**, not proof.

## Recommendation

Implement and run this one locked candidate on the bounded untouched
2020-12--2023 window.
If either test fails or is inconclusive, report that no free method tested so
far meets the USD 20 evidence contract and do not place a trade. If both pass,
the result still establishes only historical source-feed evidence. Genuine
promotion requires fresh authenticated Practice quotes, the account-specific
instrument specification and financing, and untouched broker transactions.

The method is worth testing because its signal family has substantially better
primary evidence than an ad hoc intraday classifier. It is not a promise of
income, and increasing risk until a backtest reaches USD 20 would be precisely
the hallucinated proof this workflow is designed to prevent.
