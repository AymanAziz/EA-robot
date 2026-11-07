# Stock quality weekly target result

Evaluation date: 2026-11-07

## Decision

**FAIL. No paper order was submitted.**

The preregistered 80% developed-market / 20% Big Robust portfolio did not
demonstrate average net profit above USD 20 per week on a fixed USD 10,000 base
in either locked retrospective window. More than half of its weeks were
profitable, but that is not enough to satisfy the dollar target or the
confidence tests.

## Frozen method

- Portfolio: 80% developed market and 20% value-weighted Big Robust.
- Benchmark: 100% developed market, reconstructed as `Mkt-RF + RF`.
- Rebalance: quarterly, at the close of the first common observation in each
  calendar quarter.
- Costs: 0.10% annual market drag, 0.50% annual Big Robust drag, and 10 bps per
  one-way traded notional at entry, rebalance, and final liquidation.
- No leverage or shorting.
- Weekly result: each seven-calendar-day return multiplied by the same USD
  10,000 base; later compounded equity cannot inflate the weekly target.
- Confidence: 10,000-sample paired circular block bootstrap, seed 42.
- A pass required every gate to pass independently in both windows, including
  mean weekly profit and its one-sided 95% lower bound above USD 20, positive
  paired excess over the market and its lower bound above zero, more than 50%
  profitable weeks, and the preregistered risk gates.

## Results

| Metric | Test A | Test B |
|---|---:|---:|
| Locked dates | 1991-07-01 to 2007-12-31 | 2008-01-01 to 2025-12-31 |
| Complete weeks | 861 | 939 |
| Mean weekly net P/L on USD 10,000 | **USD 19.56** | **USD 18.00** |
| One-sided 95% lower mean | USD 9.20 | USD 4.67 |
| Mean weekly excess over market | USD 0.17 | USD 0.43 |
| One-sided 95% lower excess | -USD 0.40 | -USD 0.12 |
| Profitable weeks | 57.96% | 59.85% |
| Ending equity | USD 45,421.56 | USD 41,721.75 |
| Market benchmark ending equity | USD 44,690.12 | USD 39,836.77 |
| CAGR | 9.61% | 8.26% |
| Maximum drawdown | -47.82% | -53.70% |
| Market maximum drawdown | -48.10% | -54.65% |
| Status | **FAIL** | **FAIL** |

Both tests failed these same preregistered gates:

- mean fixed-base weekly net P/L above USD 20;
- one-sided 95% block-bootstrap lower mean above USD 20; and
- one-sided 95% paired-bootstrap lower excess above the market.

The result therefore does not establish a USD 20 weekly edge. The positive
historical CAGR and greater-than-50% profitable-week rate do not override the
failed target and confidence gates.

## Data and reproducibility

The test used the official Kenneth French Data Library daily files:

- [Developed five factors, daily](https://mba.tuck.dartmouth.edu/pages/faculty/Ken.French/ftp/Developed_5_Factors_Daily_CSV.zip)
  (`f6c5ceea945f4c2829025fc654d6a878041eba85765c88ee05ba34640f622831`)
- [Developed six size/profitability portfolios, daily](https://mba.tuck.dartmouth.edu/pages/faculty/Ken.French/ftp/Developed_6_Portfolios_ME_OP_Daily_CSV.zip)
  (`4cc284b9bd6450f4e3717fe8e1824efef3d53af1c7caaa9dc02c2c14824433`)
- [Dartmouth construction details](https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/Data_Library/six_portfolios_profitability_developed.html)

Private artifacts are stored under `var/stock_quality/` and are intentionally
excluded from Git. The cache contains the two raw ZIP payloads, pins their
SHA-256 values, and reparses them on every load before accepting the normalized
rows. Reproduction command:

```bash
papertrade stock-quality-target \
  --cache var/stock_quality/developed_daily_cache.json \
  --report var/stock_quality/target_report.json
```

Three consecutive cache-only runs produced the identical report-file SHA-256:
`d4a539aae8fe17daa232bac2aa76d7d3a0ba98465b02dba12fc4edaef19df8e5`.
The private raw-bound cache SHA-256 is
`3dc8683a3b8c7cf0c67917688b24131add87bbdb8463e3d9960044357ca5a0b5`;
the report's internal canonical hash is
`b2eada5b44d0f11e560c33b280102ed30624e463abd6d02e70f25d45c46ed60d`.
The frozen specification hash is
`c20eeca7b7c4ea110236c3375c12eac7eeeb944c410a21659a1e676a611dab15`;
the prepared-data hash is
`b10101434ced0d205b4ac032ef4c20448a005d8cb3edd4a86f05ceddf905cb6b`.
Both cache and report are written with mode `0600`.

## Limits and next decision

Big Robust is a historically formed published research portfolio, not an
investable security or a constituent-level reconstruction. The test is
retrospective and cannot prove future profit. Changing the weight or costs now
to force a pass would be post-result tuning on the same data, not independent
evidence. A defensible next attempt needs a newly preregistered method and
untouched validation data, or prospective paper observation; this failed result
does not authorize a trade.
