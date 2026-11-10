# GOLDNIX V3: legitimate paths after the failed Step-6 gate

Checked on 2026-11-10. This note asks whether another method can **ensure** an
approval under the existing G1-G9 rules without changing a failed result after
the fact. It does not open the holdout and does not modify either frozen study.

## Conclusion

No method can legitimately guarantee a Step-6 pass. The gate values are
statistics computed from future outcomes, not settings that engineering can
force. Searching the same 2005-2025 sample until a configuration passes would
turn the pass into a selected in-sample result. The backtest-overfitting
literature specifically treats selection across many simulated strategies as
the problem to measure, and finance research documents that multiple testing
requires a higher evidentiary hurdle.
[Probability of Backtest Overfitting](https://papers.ssrn.com/sol3/Papers.cfm?abstract_id=2326253),
[multiple-testing methods in finance](https://academic.oup.com/raps/article/10/2/199/5817321)

There are legitimate ways to improve the *chance* of a future V3 passing:
lower the executable cost and minimum contract exposure, start from an
externally motivated signal rather than a parameter search, retain enough
entry density, and lock the complete protocol before exposing new XAUUSD
outcomes. None guarantees approval.

## What the completed V2 says

The accepted broker-time V2 output is
[`goldnix_v2/out/run_5f16e32256eb/metrics.json`](../goldnix_v2/out/run_5f16e32256eb/metrics.json).

| Constraint | V2 result | Existing pass rule | Consequence |
| --- | ---: | ---: | --- |
| Pooled mean R | +0.02825R | bootstrap lower bound > 0 | Point mean is positive, but G1 lower bound is -0.06164R. |
| Signal minus baseline | +0.11522R | point >= +0.10R and lower bound > 0 | G2 passes; G3 lower bound is still -0.00843R. |
| Positive eras | 2/4 | at least 3/4 | Era A and B remain negative. |
| Baskets | 677 | at least 1,000 | V2 is 323 baskets short and receives `INSUFFICIENT DATA`. |
| Observed frequency | 32.89/year | 48.58/year over the same 20.59 years | A V3 must retain substantially more signals than V2. |
| One-year p99 drawdown | $90.67 | <= $2.40 for a $20 account | The current minimum lot fails G7 by a wide margin. |

At the same V2 drawdown distribution, G7 alone requires about **$755.62** of
equity because $90.67 / 12% = $755.62. That does not repair G1, G3, G4 or G5.

Reaching exactly 1,000 baskets would not by itself establish G1. As a rough
planning calculation only, treating the observed bootstrap SE as scaling with
the inverse square root of independent basket count gives an implied basket
standard deviation of 1.4439R. Holding the +0.02825R mean fixed would require
about 7,069 baskets for a normal one-sided 5% lower bound above zero. That is
roughly 194 additional years at V2's observed rate. This is **not a forecast**:
the mandated monthly block bootstrap, serial dependence and future effect size
can give a different answer. It shows why merely adding 323 similar baskets is
not an evidence-based cure.

## Paths that are legitimate

### 1. Fix minimum-lot feasibility before signal research

MetaTrader exposes minimum deal volume, volume step and contract size as
broker-supplied symbol properties. Orders below `SYMBOL_VOLUME_MIN`, or not on
`SYMBOL_VOLUME_STEP`, are invalid; `SYMBOL_TRADE_CONTRACT_SIZE` determines the
one-lot contract. Therefore the only structural ways to reduce dollar exposure
below the current 0.01-lot trade are a genuinely smaller contract specification
or no trade. Leverage does not shrink price P/L per contract.
[MetaTrader permitted volumes](https://www.mql5.com/en/book/automation/symbols/symbols_volume),
[official symbol properties](https://www.mql5.com/en/docs/constants/environment_state/marketinfoconstants)

Before a V3 backtest, export these properties from every candidate demo venue:

- `SYMBOL_VOLUME_MIN`, `SYMBOL_VOLUME_STEP`, `SYMBOL_TRADE_CONTRACT_SIZE`;
- profit and loss tick values and tick size;
- actual H1 bid/ask history and floating-spread status.

A venue with a smaller true contract can address G7 without inventing a lot
size the broker will reject. It creates a new execution specification and must
be modelled from that venue's own quotes. It cannot guarantee G1-G5.

### 2. Use cost as a venue qualification, not an optimized threshold

The earlier zero-spread sensitivity and V2 show that transaction costs are
material. A future protocol can qualify venues in advance using a cost budget,
then test exactly one locked venue/rule combination. Passive orders are not a
free-spread assumption: MetaTrader documents that permitted order and filling
modes are server properties, and real-time execution is not guaranteed at a
requested price.
[MetaTrader order and fill properties](https://www.mql5.com/en/docs/constants/environment_state/marketinfoconstants)

The historical input must contain actual target-venue bid/ask quotes. Replacing
them with zero spread, assuming every limit order fills, or choosing the
cheapest threshold after viewing returns would not be a valid Step-6 result.

### 3. Develop one externally motivated, higher-density V3

Published research gives a rationale for time-series trend signals across
commodities and other futures, but the reported persistence is mainly at
one-to-twelve-month horizons; it does not prove an H1 gold edge.
[Moskowitz, Ooi and Pedersen, *Time Series Momentum*](https://www.sciencedirect.com/science/article/pii/S0304405X11002613)
Later primary research finds weaker asset-by-asset and out-of-sample evidence,
which is a reason to require the unchanged baseline and bootstrap rather than
treat momentum as established for XAUUSD.
[Huang et al., *Time series momentum: Is it there?*](https://www.sciencedirect.com/science/article/pii/S0304405X19301953)

If V3 is attempted, its design should:

1. preserve at least 48.58 completed baskets per year in planning, because a
   hard H4 filter already made G5 impossible on the existing span;
2. define at most one small, literature-anchored signal family before new
   XAUUSD outcomes are read;
3. keep random entries direction- and eligibility-matched;
4. disclose V1 and V2 as prior trials in any multiple-testing assessment; and
5. retain fixed transaction costs, gap policy, monthly block bootstrap and all
   G1-G9 thresholds.

An example research direction—not a claim of edge—is an ensemble that retains
the original H1 Aroon candidates while using a predeclared slow trend measure
as a score rather than V2's hard discard filter. Because 0.01 lot cannot be
scaled downward, score-to-size mapping would be binary at the current venue;
the venue/minimum-contract problem must therefore be solved first. The exact
score and horizon cannot now be selected by comparing their 2005-2025 returns.

### 4. Treat volatility management as risk control, not edge creation

Primary research reports benefits from reducing exposure when estimated
volatility is high. That supports a prospective risk policy, but it does not
repair a negative or statistically uncertain entry signal.
[Moreira and Muir, *Volatility Managed Portfolios*](https://www.nber.org/papers/w22208)
With a broker minimum of 0.01 lot, the required lower exposure can be zero.
That can lower drawdown while also reducing baskets and making G5 harder.

### 5. Reset validation with genuinely unexposed outcomes

The 2005-2025 sample has now influenced V1 and V2. It can remain an exploratory
development record, but another winner selected from it is not independent
confirmation. A legitimate V3 requires:

- a written decision config and complete trial registry before testing;
- development on data that will not be used as the final XAUUSD verdict, such
  as separately declared markets or an earlier training partition;
- a new, sequestered XAUUSD evaluation period that is run once; and
- a later forward-demo period for broker execution parity.

The current holdout must remain unopened unless the project explicitly retires
the old protocol and declares that period as V3 development data. If that is
done, it is no longer a holdout, and a later untouched period must replace it.
Model sequestration—announcing the strategy before later observations—is one
of the published defenses against backtest overfitting.
[Bailey et al., backtest-overfitting discussion](https://www.davidhbailey.com/dhbpapers/overfitting.pdf)

## Things that cannot honestly create approval

| Proposed shortcut | Why it is invalid or insufficient |
| --- | --- |
| Lower G1-G9 thresholds | Changes the question after seeing failure. |
| Try thresholds until one passes | Multiple testing on the verdict sample; the selected pass is not an independent result. |
| Change bootstrap or Monte Carlo seeds | Searches random-number realizations rather than measuring uncertainty. |
| Assume zero spread or guaranteed passive fills | Replaces executable economics with an unattainable fill model. |
| Increase lots after wins or cut after losses | Does not improve mean R or signal-minus-baseline; 0.01 lot is already the floor. |
| Increase the declared account balance without funding it | Falsifies G7's input and still leaves G1, G3, G4 and G5 failing. |
| Add more copies of existing trades | Does not add independent information. |
| Open the holdout repeatedly | Converts the holdout into training data. |

## Recommended decision

Do not implement another same-sample V3 with the objective “make Step 6 pass.”
First qualify a venue/account whose true minimum contract can satisfy the risk
envelope. Then register one higher-density, externally motivated V3 and its
complete trial count, and reserve genuinely new XAUUSD data for a single
evaluation. The result may pass or fail; that uncertainty is what makes the
approval meaningful.

