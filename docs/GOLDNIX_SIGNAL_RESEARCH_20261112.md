# Goldnix: bounded signal hypotheses after V1/V2

Researched on 2026-11-12 using original authors' papers, a university research
record, and an original strategy author's article. No strategy was run for
this note, no 2026 data was inspected, and no frozen source was modified.

The useful next study is a small, disclosed comparison of **slow-trend pullback
entries and rolling-channel breakouts**, with the existing Aroon variants as
controls. These are hypotheses for a new exploratory study, not published
proof that these H1 rules pass Step 6. More indicator trials cannot solve an
unqualified minimum contract or make previously examined data independent.

## What the primary evidence supports

| Source | Finding relevant to this project | Limit on transfer |
| --- | --- | --- |
| Batten, Lucey, McGroarty, Peat and Urquhart, *Does intraday technical trading have predictive power in precious metal markets?* (2018) | Their gold analysis found some predictive parameter combinations and better results with longer MA histories; conventional parameter choices did not show predictive power. | It does not validate our EMA100/200, RSI2 trigger, ATR exits or broker costs. Parameter selection is itself part of the evidence problem. [Author university record and accepted manuscript](https://eprints.soton.ac.uk/411993/), [DOI](https://doi.org/10.1016/j.intfin.2017.06.005). |
| Szakmary, Shen and Sharma, *Trend-following trading strategies in commodity futures: A re-examination* (2010) | Studies dual-MA and channel rules across 28 commodity futures markets over 48 years, with positive net results for many markets and parameterizations. | Uses a monthly dataset. This motivates a rule family, not an H1 gold parameter choice or expected return. [Original paper](https://www.sciencedirect.com/science/article/pii/S037842660900199X). |
| Larry Connors, original Improved R2 article (2007) | Combines a 200-day trend condition with a short RSI-based pullback trigger on the S&P 500. | A practitioner backtest on daily equities; its exact multi-day trigger and RSI exit differ from our proposed H1 crossings and ATR exits. Its advertised win rate must not be transferred to gold. [Original author's article](https://tradingmarkets.com/recent/the_improved_r2_strategy_84_correct_with_just_6_rules_-674361). |
| *Performance of intraday technical trading in China's gold market* (2022) | Finds that apparently attractive rules do not reliably retain performance after costs, data-snooping controls and out-of-sample selection. | Uses five-minute Chinese futures and a particular sample/rule universe. It is conflicting evidence, not proof every possible gold rule fails. [Original paper](https://www.sciencedirect.com/science/article/pii/S1042443121001876). |

## Family 1: slow-trend pullback recovery

**Research hypothesis:** short adverse excursions within a slower trend may
offer a different entry distribution from buying an Aroon breakout. Repeated
pullback recoveries permit re-entry without waiting for the slow trend to
change sign. The exact rules below are a project adaptation, not rules or
returns asserted by the sources above.

Use midpoint closes `C[t]`, a causal EMA `E[t]`, and Wilder RSI(2), all evaluated
only after H1 bar `t` closes:

- BUY when `C[t] > E[t]` and RSI crosses from `<= q` on `t-1` to `> q` on `t`.
- SELL when `C[t] < E[t]` and RSI crosses from `>= 100-q` to `< 100-q`.
- Otherwise emit no signal. Entry occurs at the next actual bar's open using
  the existing ask/bid fill convention.
- For the proposed bounded study, EMA length `{100, 200}`, `q={10,20}`, and
  stop `{1,2}` times ATR give **eight** variants. Target distance is twice the
  stop distance; the rest of the engine/risk envelope remains fixed.
- RSI is initialized explicitly; flat gains and losses must not produce
  spurious entries. Set a minimum history and a fixed EMA warm-up before
  examining results, and discard all warm-up trades.

The crossing-out trigger differs from simply entering while RSI is extreme.
Do not silently switch between the two after results are known. Nor should
EMA versus SMA, smoothing seeds, or slope conditions become unrecorded trials.

The EMA-side condition is direction eligibility, so the random baseline must
match it. Otherwise an apparent edge could be due to trading only above/below
the trend measure, rather than selecting pullback recoveries within that same
eligible opportunity set. Matching long/short counts alone is insufficient.

## Family 2: rolling-channel breakout

**Research hypothesis:** a direct price-range break can enter sustained moves
at a different time from the Aroon oscillator. This is the channel family
motivated by the commodity trend literature; its H1 adaptation is unvalidated.

For lookback `N`, calculate a channel from the **previous N completed bars**:

```text
upper[t] = max(mid_high[t-N : t])   # t excluded
lower[t] = min(mid_low [t-N : t])   # t excluded

BUY:  C[t] > upper[t] and C[t-1] <= upper[t-1]
SELL: C[t] < lower[t] and C[t-1] >= lower[t-1]
```

Execute at `open[t+1]`, preserving actual entry spread and stop-first behavior.
No entry price may be placed retrospectively at the channel boundary inside
the signal bar. An example fixed grid is `N={24,48,72,120}` with stop
`{1,2}` ATR and target twice the stop, giving eight variants. Register the exact
four lookbacks in the study manifest before running them; the literature does
not justify picking the best-looking values afterward.

Use one clearly declared breakout-event convention throughout. Emitting a
signal at every new channel high is different from the crossing convention
above. Such a change is another trial, not an implementation-neutral detail.

## Family 3: session momentum, deferred for this H1 study

Baltussen, Da, Lammers and Martens (2021) find that returns before the final
half-hour predict the final half-hour across futures markets. Their gold sample
uses COMEX hours 08:20–13:30, with the relevant final half-hour at 13:00–13:30
New York time. The paper also reports later reversals and explains the effect
through hedging demand. [Author-hosted original paper, Appendix A3 and Sections
2–3](https://academicweb.nd.edu/~zda/intramom.pdf).

That suggests a possible one-trade-per-session study, but the present UTC H1
OHLC cannot reconstruct the 13:30 price or isolate the half-hour high/low.
Using the 13:00–14:00 bar, or allowing fixed ATR exits for several hours, would
test a different hypothesis. Do not claim replication. Defer this family until
appropriate bid/ask M30 or finer data and explicit historical session/calendar
handling are available. No H1 session proxy is recommended for the current
24-candidate budget.

## Density, evaluation and trial accounting

The declared 2005-06-01 to 2026-01-01 exclusive trade span is 20.5863 calendar
years. Reaching 1,000 completed baskets requires an average **48.58 baskets
per year**. This arithmetic was computed from the dates, not estimated from a
backtest. No source above establishes that either candidate actually reaches
that count after costs, one-position restrictions, holidays and daily halts.
Measure completed baskets; repeated signals are not extra trades.

The proposed full bounded comparison has eight existing-family Aroon controls,
eight pullback variants and eight channel variants. Record each specification,
code/config/data hash, every failure, and all results. Preserve the original
G1–G9 gate calculations, report a selection-adjusted mean bound separately,
and do not silently replace the declared 5% single-strategy gate with a
different test. Bonferroni can account conservatively for dependent tests when
their individual error bounds are valid; a 24-trial correction still does not
account for undisclosed earlier trials or turn reused data into untouched data.

All 2005–2025 performance has already participated in the research process.
Any selected same-history pass is an exploratory numerical result. It is not
new independent evidence. Keep the previously opened 2026 holdout out of this
search and reserve a new validation design before further evaluation. The
original PBO work explicitly addresses the danger of selecting among many
historical simulations. [Bailey et al., original paper](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf).

Retain the original spread/gap/fill rules, monthly blocks, per-era reporting,
random-entry execution envelope and UTC daily halt for every candidate. Any
additional commission, financing or executable-exposure evidence should be
reported explicitly. There is no evidence here that changing the entry signal
alone makes a $20 account feasible at the current minimum gold contract.

## Source-access notes

The original author-hosted momentum and PBO PDFs and Connors' original article
were retrieved directly. Southampton's university record and both Elsevier
abstracts were available through the indexed first-party pages; subsequent
direct fetches returned HTTP 403. No claims rely on unrelated strategy blogs,
forum performance numbers, or the recent promotional gold-system preprints
surfaced in search.
