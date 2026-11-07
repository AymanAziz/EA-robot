# OANDA Practice XAU/USD evidence and double-test contract

Official sources and the repository were checked on 2026-11-07. No credential
was read, no market result was invented and no order was submitted.

## Verdict

OANDA's v20 instrument identifier is `XAU_USD`: OANDA names the product
`XAU/USD`, while its API defines an instrument name as base and quote separated
by `_`. This is a documented derivation, but the authenticated account response
must remain authoritative. OANDA says the account-instruments list depends on
the account's regulatory division; Singapore offers XAU/USD, while OANDA's US
help explicitly says it does not offer gold. Enable it only when the Practice
account returns exactly `name: "XAU_USD"` from the account-instruments endpoint.
[OANDA XAU/USD](https://www.oanda.com/sg-en/trading/instruments/xau-usd/),
[instrument-name schema](https://developer.oanda.com/rest-live-v20/primitives-df/),
[account instruments](https://developer.oanda.com/rest-live-v20/account-ep/),
[US gold notice](https://help.oanda.com/us/en/MicroContent/Resources/MicroContent/OC/new-phrase-2-1.htm)

Gold must not silently inherit ordinary forex assumptions. OANDA describes the
product as a gold CFD, and the v20 schema distinguishes `METAL` from `CURRENCY`
and `CFD`; record the account response's actual `type`. Product availability,
sessions and financing can differ by division. OANDA also excludes OANDA Global
Markets and OANDA TMS Brokers accounts from v20 API access.
[product classification](https://www.oanda.com/sg-en/trading/instruments/xau-usd/),
[instrument types](https://developer.oanda.com/rest-live-v20/primitives-df/),
[v20 eligibility](https://developer.oanda.com/rest-live-v20/introduction/)

The current no-credential backend cannot produce a genuine OANDA gold result.
The broker factory disables OANDA without both a Practice token and account ID,
the only credential-free history adapter supports BTC/USD and ETH/USD, and the
instrument/protection allowlists currently contain only EUR/USD and GBP/USD for
OANDA. See the [broker factory](../src/papertrade/brokers/factory.py),
[public data adapter](../src/papertrade/data.py),
[instrument registry](../src/papertrade/domain.py) and
[OANDA adapter](../src/papertrade/brokers/oanda.py). OANDA itself requires
authentication for the Practice REST origin. A no-credential XAU/USD result
would therefore be synthetic or from a different provider, not OANDA evidence.
[Practice API](https://developer.oanda.com/rest-live-v20/development-guide/),
[authentication](https://developer.oanda.com/rest-live-v20/authentication/)

## Read-only account preflight

Credentials belong only on the Oracle VM. The first request after they exist is
read-only:

```text
GET https://api-fxpractice.oanda.com/v3/accounts/{accountID}/instruments?instruments=XAU_USD
Authorization: Bearer <personal-access-token>
```

Stop if the response is empty, has another name, or the account is not an
eligible v20 Practice account. Persist a timestamped snapshot of these returned
values instead of guessing or copying web examples:

- identity and classification: `name`, `displayName`, `type`;
- price rules: `pipLocation`, `displayPrecision`;
- size rules: `tradeUnitsPrecision`, `minimumTradeSize`,
  `maximumOrderUnits`, `maximumPositionSize`;
- risk rules: `marginRate`, `minimumTrailingStopDistance`,
  `maximumTrailingStopDistance`, `minimumGuaranteedStopLossDistance`,
  `guaranteedStopLossOrderMode`, execution premium and level restriction;
- costs: `commission`, financing `longRate`, `shortRate` and
  `financingDaysOfWeek`.

These are fields in OANDA's account-returned `Instrument` object, including
account-specific guaranteed-stop behavior and financing.
[instrument schema](https://developer.oanda.com/rest-live-v20/primitives-df/)
The account pricing endpoint must separately supply current `bids`, `asks`,
liquidity, `tradeable` and home-currency conversion factors.
[account pricing](https://developer.oanda.com/rest-live-v20/pricing-ep/)
The existing adapter's unconditional whole-unit rule and forex constants are not
evidence that gold has the same unit step, precision, spread or stop rules.

## Genuine candle contract and limits

The adapter's `GET /v3/instruments/{instrument}/candles` route is in OANDA's
official OpenAPI; current developer documentation also lists the account-scoped
`GET /v3/accounts/{accountID}/instruments/{instrument}/candles`. Both are
authenticated. Use `M15`, `smooth=false`, a bounded `from`/`to` interval and
`includeFirst=false` after the first page. Request bid and ask components (`B`
and `A`, optionally midpoint `M`) and admit only `complete: true` candles.
[official OpenAPI](https://github.com/oanda/v20-openapi/blob/master/yaml/separate/v20_instrument.yaml),
[current candle endpoint](https://developer.oanda.com/rest-live-v20/pricing-ep/)

OANDA documents M15 as a supported 15-minute granularity and a maximum of 5,000
candles per request. With `from` and `to`, `count` should be omitted; paginate
explicitly and de-duplicate boundary timestamps. OANDA describes v20 history as
complete and generally available back to 2005, but that is not a guarantee that
`XAU_USD` begins in 2005 for this account. Record the first and last returned
candle, gaps, request parameters and a dataset hash.
[candle definitions](https://developer.oanda.com/rest-live-v20/instrument-df/),
[history limits](https://developer.oanda.com/rest-live-v20/api-comparison/),
[v20 introduction](https://developer.oanda.com/rest-live-v20/introduction/)

Candle `volume` is the number of prices created during the interval, not
centralized traded notional. Historical candles are also base-price-group data;
OANDA warns that the account's live pricing group can differ. Historical bid/ask
candles can estimate spread, but only forward account quotes and Practice fills
test account-specific execution.
[candle volume](https://developer.oanda.com/rest-live-v20/instrument-df/),
[historical versus live pricing](https://help.oanda.com/us/en/faqs/rest-v20-api-troubleshooting-guide.htm)

Gold testing must charge observed spread, returned commission, conservative
slippage and any financing incurred across the daily cutoff. OANDA says gold CFD
financing has distinct long and short rates, can change daily and can represent
multiple days around weekends or holidays. A midpoint-only backtest with zero
financing is not an after-cost result.
[OANDA financing costs](https://www.oanda.com/sg-en/trading/financing-costs/)

## Two independent tests

The two tests are an untouched chronological test and a subsequent forward
Practice test. Running the same saved backtest repeatedly only checks
determinism; it does not create independent evidence.

1. **Locked historical test.** After data/spec preflight, preregister the
   instrument snapshot, one-hour four-bar horizon, date range, feature/model
   settings, threshold grid, position policy and every cost. Keep the existing
   chronological 50% train / 15% calibration / 15% threshold-validation / 20%
   final-test split and purge rules. The final slice may be read once. Require
   the repository's existing gates: minimum validation and test trade counts,
   positive after-cost returns, benchmark outperformance, bounded drawdown,
   positive Sharpe, a positive lower bootstrap mean trade P/L and at least two
   profitable walk-forward folds. Thirty trades is the software's minimum gate,
   not strong statistical proof. See the
   [research contract](DATA_ML_SOURCES.md).

2. **Untouched forward Practice test.** Freeze the accepted model, threshold,
   cost policy and code before it starts. Use fresh account bid/ask quotes and
   timestamped OANDA Practice transactions; do not tune on these observations.
   Predeclare the calendar duration and closed-trade target using a one-sided
   binomial power calculation for a stated minimum effect, alpha and power.
   Exclude overlapping trades or adjust inference for their dependence, and do
   not stop early merely because the point estimate crosses 50%. Require the
   win-rate confidence bound and all after-cost P/L, drawdown and risk gates.
   Insufficient observations means **inconclusive**, not pass.

## What “above 50%” may mean

`ROC-AUC > 0.50` means the prediction scores rank the two outcome classes better
than chance in that sample. It is not a 50% probability of winning a trade and
does not include spread, slippage, commission or financing. Scikit-learn defines
ROC-AUC as area under the ROC curve from prediction scores and notes random
guessing has AUC 0.5 in expectation.
[scikit-learn ROC-AUC](https://scikit-learn.org/stable/modules/generated/sklearn.metrics.roc_auc_score.html)

`trade win rate > 50%` means profitable closed trades divided by all closed
trades after costs. Report the numerator, denominator and a predeclared 95%
confidence interval; require its lower bound to exceed 50% for that claim. Even
then, a high win rate can lose money when losses exceed wins, so positive net
P/L after every cost and acceptable drawdown remain mandatory. Report AUC and
trade win rate separately and never relabel one as the other.

## Blocker

The evidence chain stops before data collection: the inspected backend has no
OANDA Practice token/account, and the code does not yet register or safely model
XAU/USD as a metal CFD. Until the Oracle VM has the credentials, the read-only
account query confirms `XAU_USD`, and the returned specifications are integrated
and tested, there is no genuine gold backtest, no Practice trade and no honest
claim of a win rate above 50%.
