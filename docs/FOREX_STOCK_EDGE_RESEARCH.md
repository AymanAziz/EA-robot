# Forex, stocks and the search for a legitimate market “loophole”

Research completed on 2026-11-07. This report assumes a USD 10,000 account and
the objective of averaging more than USD 20 per week. It is research, not a
promise of income or authorization to place a trade.

## Direct answer

USD 20 per week is USD 1,040 per year, so the account must earn **10.4% a year
before fees and tax**. No persistent, retail-accessible loophole was found that
can deliver that return without meaningful risk.

There are genuine effects that can be called **edges**—the equity risk premium,
value, momentum, currency carry and trend—but they are compensation for risk,
behavioral effects or implementation difficulty. They can disappear for years
and sometimes crash. True arbitrage also exists, but the cited examples require
institutional funding, direct market access, large creation units, low latency
or balance-sheet capacity. Those are the barriers that keep the apparent free
money from being free to a USD 10,000 retail account.

My conclusion is:

- **Stocks are the better default.** A diversified stock index owns productive
  companies and has a positive long-run return source, although it can lose
  half its value in a severe drawdown.
- **Forex is the weaker retail choice.** A defensible FX strategy must diversify
  across currencies and harvest carry or medium-term trends. Leveraged
  single-pair scalping is not the loophole.
- **A stock core plus a small, independently tested multi-asset trend sleeve is
  the strongest research direction.** It still cannot make USD 20 every week
  or guarantee a 10.4% annual average.

Implemented follow-up: the preregistered 80% developed-market / 20% Big Robust
quality test failed the USD 20 target in both locked windows. See
[the stock-quality target result](STOCK_QUALITY_TARGET_RESULT.md). The failure
does not invalidate stocks as the better default; it rejects this specific
quality tilt as proof of the requested weekly edge.

## Forex versus stocks

| Question | Diversified stocks | Retail OTC forex |
|---|---|---|
| Long-run return source | Company earnings, reinvestment and distributions | Relative currency moves plus the interest-rate differential |
| Best-supported approach | Low-cost broad index; patient factor exposure is optional | Diversified carry and medium-horizon trend across several currencies |
| Main danger | Large market drawdowns and long recovery periods | Leverage, financing, dealer spread, crash risk and no persistent upward drift in one currency pair |
| Small-account implementation | One broad fund can provide thousands of holdings | Faithful diversification needs several pairs, careful notional sizing and accurate rollover data |
| Evidence for frequent retail trading | Generally poor after costs | Particularly poor: about two thirds of registered-dealer retail accounts lose in a typical quarter |
| Verdict for USD 10,000 | Better choice, but the return target remains uncertain | Research-only unless a frozen multi-currency method survives realistic forward testing |

MSCI ACWI currently covers 2,413 companies across 23 developed and 24 emerging
markets. Its gross USD return was 8.83% annualized since 1987, below the 10.4%
target, with a 58.06% maximum drawdown. Its more recent ten-year return was
12.93%, showing why a favorable recent period must not be treated as a promise.
[MSCI ACWI factsheet](https://www.msci.com/documents/10199/255599/msci-acwi.pdf)

The CFTC reports that roughly two out of three retail OTC forex traders lose
money each quarter. It also explains that the customer trades against the
dealer and that spreads, financing and fees count against the customer. The
2025 BIS survey puts OTC FX turnover at USD 9.6 trillion per day; 59% of
execution was electronic, and dealers internalised more than 80% of customer
trades. The inference is that a retail bot is competing in a deep, automated,
professional market while receiving dealer-specific execution—not discovering
an unattended public price error.
[CFTC forex warning](https://www.cftc.gov/LearnAndProtect/forexfrauds),
[BIS 2025 FX turnover](https://www.bis.org/statistics/rpfx25_fx.pdf),
[BIS execution landscape](https://www.bis.org/publications/qr-202512/fx-trade-execution-landscape-through-prism-2025-bis-triennial-survey)

## Candidate edges, ranked by retail usefulness

### 1. Broad stock-market exposure — strongest default, not a loophole

A broad, low-cost index is the most implementable approach because it captures
the market return without needing to identify the next winning stock. Current
SPIVA data show that 83.33% of U.S. large-cap funds underperformed the S&P 500
over ten years and 90.49% underperformed over fifteen years through June 2026.
This does not prove an index will earn 10.4%; it shows how difficult it has been
for professional active managers to improve on the index after their costs.
[S&P SPIVA scorecard](https://www.spglobal.com/spdji/en/research-insights/spiva/)

For an individual account, trading less is itself a measurable advantage over
high turnover. Barber and Odean studied 66,465 brokerage households: the
highest-turnover group earned 11.4% annually during the sample while the market
earned 17.9%. That historical period had unusually strong market returns, so
the relevant result is the large shortfall caused by active behavior and costs,
not the absolute 11.4% number.
[original household-trading study](https://faculty.haas.berkeley.edu/odean/papers/returns/individual_investor_performance_final.pdf)

**Assessment:** best real-money foundation, but it may average less than USD 20
per week and will have negative weeks and years.

### 2. Global quality and momentum stocks — closest practical stock edges

Two transparent global factor indexes historically cleared the 10.4% hurdle,
but neither establishes a future return expectation:

- MSCI ACWI Quality selects companies using return on equity, stable earnings
  growth and low financial leverage. It returned 11.76% annualized gross from
  June 1994 through October 2026, equivalent to USD 22.62 per week on USD
  10,000. Its maximum drawdown was 49.59% and latest annual turnover was
  23.05%. The index launched in December 2012, so its earlier history is
  backtested. Its current top ten holdings make up 40.07% and information
  technology is 41.29%, creating concentration risk.
- MSCI ACWI Momentum returned 12.19% annualized gross over the same broad
  interval, equivalent to USD 23.44 per week, but had a 60.44% maximum drawdown
  and 117.24% latest annual turnover. It launched in February 2013, so the
  earlier result is also backtested.

[MSCI ACWI Quality factsheet](https://www.msci.com/documents/10199/255599/msci-acwi-quality-index.pdf),
[MSCI ACWI Momentum factsheet](https://www.msci.com/documents/10199/255599/msci-acwi-momentum-index.pdf)

**Assessment:** quality is the cleaner single stock factor to test because its
historical turnover and drawdown were lower than momentum's. A limited quality
or quality-and-momentum tilt around a broad index is more defensible than
replacing the whole portfolio. The returns are gross, partly backtested and can
still involve losing half the capital temporarily, so this is not proof of USD
20 per week.

### 3. Diversified momentum/trend — real evidence, irregular payoff

Momentum exists in both stocks and currencies. The Kenneth French data library
publishes long histories and construction details for stock momentum factors.
Research over more than a century finds value, momentum, carry and defensive
premia across asset classes, but estimates fall about 30% out of sample and
factor-timing profits become very small after realistic data lags and trading
costs. Stock momentum can also suffer infrequent, persistent crashes.
[Kenneth French factor data](https://mba.tuck.dartmouth.edu/pages/faculty/Ken.French/data_library.html),
[century of factor evidence](https://www.aqr.com/Insights/Research/Journal-Article/How-Do-Factor-Premia-Vary-Over-Time-A-Century-of-Evidence),
[momentum-crash study](https://www.nber.org/papers/w20439)

In currencies, the original BIS-hosted study found cross-sectional momentum,
but transaction costs explain part of the return. The stronger application for
this project is therefore a slow, diversified signal across multiple liquid
markets rather than a high-turnover EUR/USD or XAU/USD strategy.
[BIS currency-momentum study](https://www.bis.org/publications/working-paper-366-currency-momentum-strategies)

**Assessment:** the best active family to test, but only with a frozen rule set,
several markets, conservative risk sizing and every cost included. It is an
edge, not certain income.

### 4. Currency carry — a risk premium, not free rollover

Carry borrows or sells a low-interest-rate currency and holds a higher-rate
currency. It has been profitable on average in historical research, but the
payoff is negatively skewed: abrupt unwinds occur when funding liquidity and
risk appetite deteriorate. A broker's displayed positive swap is also not the
strategy's net return; the exchange rate can move against the position, and
dealer financing and spreads must be paid.
[NBER carry-trade crash research](https://www.nber.org/papers/w14473)

The BIS-hosted currency-momentum study found as much as a 10% gross annual
winner-minus-loser spread. Applying the full quoted bid-ask spread reduced its
best strategy from nearly 10% to about 4% per year and erased most of the
profit in many other variants. The authors treat full quoted spreads as a
conservative cost assumption, but still conclude that effective limits to
arbitrage prevent the return from being easily exploited. Its implementable
object is a diversified currency portfolio, not a directional trade in one
pair.
[BIS currency-momentum study](https://www.bis.org/publications/working-paper-366-currency-momentum-strategies)

**Assessment:** legitimate only as a diversified, low-leverage portfolio. A
single “positive swap” pair is a concentrated crash and regime-change bet.

### 5. Diversified stock-factor blend — more robust, still below target

The MSCI ACWI Diversified Multiple-Factor Index combines value, momentum,
quality and smaller-company exposure. Its net index return was 9.99%
annualized from December 2000 through October 2026, about USD 19.21 per week on
USD 10,000, with a 58.48% maximum drawdown. It launched in 2015, making the
earlier history backtested. This is useful evidence that combining several
documented effects does not magically add their returns together.
[MSCI diversified multiple-factor factsheet](https://www.msci.com/documents/10199/cf31a389-7def-4fd3-8445-cabe63f5b627)

**Assessment:** potentially useful as a patient, diversified exposure; not a
bot loophole and not proof of the USD 20 target.

More broadly, a Journal of Finance study of 97 published stock-return
predictors found average portfolio returns were 26% lower out of sample and
58% lower after publication. Discovery, data mining and competition therefore
make a historical “loophole” a deliberately weak starting assumption.
[stock-anomaly decay study](https://onlinelibrary.wiley.com/doi/10.1111/jofi.12365)

## Why apparent arbitrage is not the retail loophole

### Covered-interest-parity arbitrage in forex

Differences between cash interest rates and FX forward prices sometimes create
a cross-currency basis that looks like nearly risk-free arbitrage. BIS research
attributes its persistence to institutional hedging demand and constraints on
bank balance sheets. Executing it requires matched wholesale borrowing and
lending, forwards or swaps, credit lines, collateral and settlement capacity.
A retail CFD account does not receive those funding rates or institutional
spreads.
[BIS cross-currency-basis research](https://www.bis.org/publications/qr-201609/covered-interest-parity-lost-understanding-cross-currency-basis)

### Triangular and latency arbitrage

Small inconsistencies between three FX rates or between venues can exist for
very short periods. A New York Fed example using 2007 quotes produced only
0.012% before other costs—about EUR 121 per USD 1 million—and required credit
arrangements with all three quote providers. Its measured incidence of similar
opportunities had hovered near zero since 2008. The modern market is already
dominated by electronic dealers, venue aggregation and high-frequency price
discovery. A retail order reaches the dealer after the observation and pays a
spread on each leg; execution delay, rejection or partial fills turn the
theoretical lock into an unhedged trade.
[New York Fed triangular-arbitrage analysis](https://libertystreeteconomics.newyorkfed.org/2014/03/has-automated-trading-promoted-efficiency-in-the-fx-spot-market/)

### ETF price-versus-NAV arbitrage

ETF shares can diverge slightly from the underlying basket. The SEC explains
that the mechanism closing that gap is creation and redemption by Authorized
Participants, commonly in blocks such as 50,000 ETF shares. An ordinary retail
holder can trade the ETF but cannot normally exchange a creation unit directly
with the fund.
[SEC ETF market-structure testimony](https://www.sec.gov/newsroom/speeches-statements/ts101911er-testimony-market-micro-structure-examination-etfs)

### Retail market making

Capturing the bid-ask spread sounds like a repeatable loophole, but an unfilled
limit order earns nothing and a filled order is more likely when the informed
side is moving the price against it. The SEC identifies this adverse-selection
risk and also documents that execution venue and order routing affect the
effective spread paid by investors.
[SEC order-execution guidance](https://www.sec.gov/about/reports-publications/investorpubstradexec),
[SEC execution and routing study](https://www.sec.gov/rules-regulations/2001/03/disclosure-order-execution-routing-practices)

## A test for every claimed “loophole”

Treat an idea as unproven unless all of these are true:

1. The signal is observable before the order, without future or revised data.
2. The quoted opportunity is executable at the size and price assumed.
3. It stays profitable after spread, slippage, financing, borrow, tax and fees.
4. The rule was frozen before an untouched out-of-sample test.
5. It survives multiple market regimes and a forward paper-trading period.
6. The return is not created by hidden leverage, rare crash exposure or a
   martingale position-sizing rule.
7. The broker permits the behavior and the trade can actually settle.

If an apparent edge fails one of these tests, it is normally a backtest error,
unpriced risk, an institutional trade that retail cannot execute, or marketing.

## Practical recommendation

For real capital, I would choose a broad diversified-stock core over retail
forex. The most interesting stock edge to test is a capped quality tilt, with
momentum used only as a smaller complement because of its turnover and crash
risk. For this robot project, I would research one slow **multi-asset trend**
model using liquid stock, bond, commodity and currency instruments, with no
martingale and no target-based leverage. Forex can be one sleeve, not the whole
system.

The honest way to make the USD 20 objective more dependable is to change a
constraint: add capital, contribute savings, accept a longer averaging horizon,
or lower the withdrawal target. Trying to manufacture certainty from leverage
does not close a loophole; it moves the shortfall into tail risk.
