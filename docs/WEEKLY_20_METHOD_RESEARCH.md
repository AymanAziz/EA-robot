# Internet research: methods for averaging USD 20 per week

Research completed on 2026-11-07. This report assumes the USD 10,000 paper
account used elsewhere in this project. It compares primary-source evidence; it
does not promise income, recommend a particular security, or authorize a trade.

## Bottom line

USD 20 per week is USD 1,040 per year, or a **10.4% simple annual return** on
USD 10,000 before fees and tax. Repeating a 0.2% gain every week would compound
to about 10.95%, but real returns are irregular.

No researched method can honestly guarantee USD 20 every week or a dependable
10.4% annual average. The most defensible choices depend on what “best” means:

- **Best practical long-term core:** a low-cost global equity index. It is easy
  to implement and highly diversified, but its 8.83% annualized gross return
  since 1987 did not reach the target and included a 58.06% drawdown.
- **Only simple index in this comparison whose long sample narrowly exceeded
  the target:** S&P 500 total-return buy-and-hold. Its 11.2% annualized return
  since June 1986 is equivalent to USD 21.54 per week on USD 10,000, but it had
  a 50.9% maximum drawdown. That historical average is not weekly income or a
  forecast.
- **Best research-backed active-system candidate:** diversified, multi-asset
  time-series momentum (trend following). The evidence is portfolio-wide; it
  does not support a gold-only or forex-scalping robot, and faithful retail
  implementation with only USD 10,000 is difficult.
- **Best route to dependable USD 20 income:** use substantially more capital in
  low-risk bills rather than force a 10.4% return. At current Treasury-bill
  coupon-equivalent rates, roughly USD 24,100–26,300 would be required before
  tax to produce USD 1,040 per year.

## Ranked comparison

### 1. Low-cost global equity index — best practical baseline

The MSCI ACWI currently contains 2,413 large- and mid-cap stocks across 23
developed and 24 emerging-market countries and covers about 85% of the global
investable equity universe. As of 2026-10-30, its gross USD return was 12.93%
annualized over ten years but 8.83% annualized since 1987. The latter is about
USD 16.98 per week on USD 10,000 before fund fees, tax and tracking difference.
Its maximum historical drawdown was 58.06%, and 2022 returned -17.96%.

This ranks first for a small account because a single broad, low-cost fund can
implement it without leverage, shorting or frequent trades. It does **not**
establish the requested return as a reasonable weekly withdrawal target.

[MSCI ACWI factsheet](https://www.msci.com/documents/10199/255599/msci-acwi.pdf)

### 2. Diversified multi-asset trend following — best systematic candidate

Moskowitz, Ooi and Pedersen documented time-series momentum across 58 liquid
equity-index, currency, commodity and sovereign-bond futures and forwards. A
later century study tested 67 markets using an equal combination of 1-, 3- and
12-month direction signals, monthly rebalancing, volatility sizing and a 10%
portfolio-volatility target.

For 1880–2016, that simulation reported 18.0% annualized excess return before
costs, 11.0% after estimated transaction costs, and 7.3% after both costs and a
hypothetical 2% management/20% performance fee. The authors warn that cost
estimates are uncertain and omit some possible futures roll costs. The
after-cost result fell to 6.2% during 2010–2016, and simulated trend-following
drawdowns reached roughly 25% for extended periods.

This is the strongest researched family for a rules-based robot, but its edge
comes from diversification across many markets, long and short positions, and
risk sizing. A USD 10,000 account cannot cheaply reproduce 67 futures markets;
a managed-futures fund is more practical but adds fees and tracking risk.
Single-market XAU/USD is not the published strategy.

[original Journal of Financial Economics paper](https://fairmodel.econ.yale.edu/ec439/mosk.pdf),
[century study](https://static.twentyoverten.com/593e8a9e7299b471eaecf644/SkLoGL67M/A-Century-of-Evidence-on-Trend-Following-Investing.pdf)

### 3. S&P 500 total-return index — historically enough, but concentrated and volatile

Cboe's current comparison reports an 11.2% annualized S&P 500 total return from
June 1986 through September 2026, equivalent to about USD 21.54 per week on a
USD 10,000 starting balance. The same sample includes a 50.9% maximum drawdown.
It is therefore evidence that the target has been exceeded as a long-horizon
historical average, not evidence that USD 20 can be withdrawn safely every week
or that the future return will repeat.

[Cboe BXM/S&P 500 comparison factsheet](https://cdn.cboe.com/resources/indices/factsheet/CboeGlobalIndices_BXM-Index.pdf)

### 4. Treasury bills — most predictable, but insufficient at USD 10,000

On 2026-11-06, U.S. Treasury coupon-equivalent bill rates ranged from 3.95% for
four weeks to 4.32% for 52 weeks. USD 10,000 would therefore produce roughly
USD 7.60–8.31 per week before tax if those annual rates persisted. Producing
USD 1,040 per year at those rates requires approximately USD 26,329 at 3.95% or
USD 24,074 at 4.32%. Rates can change, and availability, currency and tax are
jurisdiction-specific.

[U.S. Treasury daily bill rates](https://home.treasury.gov/resource-center/data-chart-center/interest-rates/TextView?field_tdr_date_value=2026&type=daily_treasury_bill_rates)

### 5. Covered calls — lower volatility, but below the target

The Cboe S&P 500 BuyWrite Index models holding the S&P 500 while selling a
one-month at-the-money call. Since June 1986 it returned 8.6% annualized, about
USD 16.54 per week on USD 10,000, with a 35.8% maximum drawdown. Premium income
is received in exchange for capped upside; it is not extra risk-free profit.
The same Cboe factsheet shows buy-write lagged the S&P 500 total-return index in
the long sample.

[Cboe BuyWrite factsheet](https://cdn.cboe.com/resources/indices/factsheet/CboeGlobalIndices_BXM-Index.pdf)

### 6. Retail forex/gold scalping, copy trading, grids and martingale — reject

The CFTC reports that about two out of three customers at registered retail OTC
forex dealers lost money after financing, fees and other expenses in its cited
period. OTC customers trade against the dealer, and leverage can magnify losses
beyond the deposited margin. This evidence does not prove that every strategy
loses, but it makes high-frequency forex or gold an inferior default for a
small account seeking dependable income. Martingale or grid sizing can disguise
many small wins until one large loss and was not supported by any high-trust
source reviewed.

[CFTC retail OTC forex advisory](https://www.cftc.gov/LearnAndProtect/AdvisoriesAndArticles/CustomerAdvisory_MustKnowForex.html)

## Recommendation for this project

Do not configure the robot to promise USD 20 per week. For a simple investment,
the evidence supports a low-cost global-equity core and a long time horizon. If
the objective is specifically to research an automated method, the only active
family in this review worth a new controlled test is **diversified multi-asset
trend following**, not single-market gold or forex.

Any implementation should first freeze the rules, include spreads, slippage,
financing and fund fees, use untouched out-of-sample periods, compare against a
passive index and cash, and then forward paper-trade. A historical average above
USD 20 is a research result, not proof of future weekly income.
