# Step 6 continuation

**H01_S11_M5_REPLAY passes all nine original numerical Step 6 gates.** It is the
earlier S11 H1 channel strategy, with unchanged entry rules and more detailed M5
bid/ask execution. It is a separate strategy from the user's M15/M5 retest idea.
The original U01 and all 12 new retest/hold variants failed profitability checks.

This is an exploratory historical pass. The selection-adjusted bound remains
negative, historical broker costs are unverified, and trading approval remains
false. No orders were sent during this continuation.

## Passing candidate

The strategy buys a close above the preceding 20-bar H1 channel and sells a
close below it. It retains S11's simple ATR(14), a two-ATR stop with a 0.50
price-unit minimum, and a target three times the stop distance. Original daily
loss, holiday, Friday and one-position controls remain in force.

Exposure is 0.01oz, matching the verified Cent demo's minimum 0.01 lot. S11's
original signal-close planned-risk ceiling is USD0.05 (5 USC). Gaps and the
next entry quote can exceed that estimate. This differs from the 3 USC cap of
the separate 12-variant MTF experiment.

M5 supplies execution detail. Median holding time was approximately **7.2
hours**; this result does not establish a frequent five-minute trading strategy.

## Historical results

June 2005 through December 2025, after modeled spread and before unverified
additional execution costs:

| Metric | Result |
|---|---:|
| Trades | 1,025 |
| BUY / SELL | 566 / 459 |
| Mean return | +0.1201R |
| One-sided 95% mean lower bound | +0.0385R |
| Win rate | 34.4% |
| Profit factor | 1.174 |
| Profitable eras | 4 of 4 |
| Total simulated P/L at 0.01oz | +USD4.1851 |
| Historical realized maximum drawdown | USD1.1852 |
| Simulated one-year 99th-percentile drawdown | USD1.0122 |
| Original drawdown limit | USD2.40 |

The total P/L spans the entire historical period. It is not a monthly or daily
income forecast. R is the nominal stop distance; spread and gaps can make a
loss larger than 1R.

| Gate | Value | Requirement | Result |
|---|---:|---:|---|
| G1: mean lower bound | +0.038533R | > 0 | PASS |
| G2: edge over random | +0.374848R | ≥ 0.10R | PASS |
| G3: edge lower bound | +0.297396R | > 0 | PASS |
| G4: positive eras | 4 | ≥ 3 | PASS |
| G5: trades | 1,025 | ≥ 1,000 | PASS |
| G6: material-gap share | 1.4634% | ≤ 10% | PASS |
| G7: simulated drawdown | USD1.0122 | ≤ USD2.40 | PASS |
| G8: fill-policy difference | 0 percentage points | ≤ 8 | PASS |
| G9: unchanged ATR calculation parity | Verified | Required | PASS |

G6 preserves the original Step 6 definition: gaps over four session hours or
over 60 hours when crossing a weekend. Separately, **32.9%** of trades crossed
some interval longer than five minutes. Those trades were retained and shorter
gaps were disclosed. The MTF experiment's stricter missing-M5-interval measure
must not be confused with the original material-gap gate.

G7 uses 100,000 IID one-year paths, not a margin, ruin or unseen-tail model.
G8 and G9 do not certify tick-level fills, broker tick-size rounding, historical
venue costs or a native EA implementing every strategy rule.

## Confidence and practical limits

- The supplementary lower bound accounting for 82 registered variants is
  **−0.0522R**. Its extreme bootstrap tail is noisy and does not cover every
  earlier research decision. The original raw gate rules were kept intact.
- Only **26 trades** occurred in 2021–2025. Recent evidence is thin, partly
  because the fixed cash-risk eligibility admits few high-volatility periods.
- An additional 0.10R cost on the fixed trade list lowers mean expectancy to
  +0.0201R; 0.25R changes it to −0.1299R. These diagnostics do not resimulate
  loss halts. Historical JustMarkets commissions, financing and slippage remain
  unverified.
- The last reconciled balance was USD19.7982. Its 12% drawdown threshold is
  USD2.3758, which the same G7 result also meets. Verified current contract
  size does not establish historical broker execution.
- No 2026 holdout performance was accessed. Previously consumed history cannot
  become independent validation. New subsequent observations are still needed.

## Completed work and evidence

The audit of U01's 788 entries found negative mean later quote returns at all
five declared horizons. The 12 registered MTF improvements, U02–U13, also all
failed G1, so their G2/G3 baselines were not evaluated. The separate H01 replay
was then registered as variant 82 and evaluated against all nine gates.

Before replay, all 1,025 original S11 trades were reproduced in every column.
The replay retains the same strategy entry timestamps and directions. All
matched H1/M5 entry quotes agree exactly; 38 eligible direction opportunities
lacked an exact M5 quote and were excluded from both signal/random eligibility.

Behavior tests passed. All 1,025 replay trades and 800 baseline schedules were
independently checked. Frozen artifacts, original V1/V2 results and installed
demo source/binaries were verified unchanged. The previous demo was last
verified flat with automation disabled.

- [Final review and limitations](out/final_review/REPORT.md)
- [Final metadata](out/final_review/RESULT.json)
- [Passing replay metrics](out/H01_S11_M5_REPLAY/RESULT.json)
- [Every replay trade](out/H01_S11_M5_REPLAY/trades.csv)
- [Registered replay protocol](replay_protocol.json)
- [All 12 MTF results](out/batch_12/SUMMARY.json)
- [Registered MTF protocol](protocol.json)
- [Original-entry path audit](out/path_audit/RESULT.json)
- [Dated S11 exposure bridge](out/S11_EXPOSURE_BRIDGE/RESULT.json)
- [Independent verification](out/final_review/VERIFICATION.json)
- [Primary-source research note](../docs/GOLDNIX_STEP6_RESEARCH_CONTINUATION_20261112.md)

Historical data attribution: [EVTradingLabs](https://evtradelabs.com/data),
which attributes underlying ticks to Dukascopy. These public quotes are not
independently verified historical JustMarkets prices.

Outputs refuse overwrites. Preserve every result, including failures. New
strategy changes require new registration and their own output directory.
