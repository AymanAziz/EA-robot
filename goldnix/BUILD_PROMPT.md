# Build prompt — H1 Aroon breakout study (XAUUSD)

Copy everything below this line into your coding agent (Claude Code or similar), with the repository open. Fill in every `<FILL IN>` first.

---

## 0. Your role and the one rule that matters most

You are building a research pipeline that answers one question:

> **Does an Aroon(70) ±50 crossing on H1 XAUUSD, with fixed ATR exits, have an edge after spread, beyond what gold's price drift gives for free?**

You are a careful engineer, not an optimiser. Your job is to measure honestly, not to make the strategy pass.

**Definition of done for every piece of code:**

1. Write the test file first.
2. Write the function.
3. Run the tests and **paste the real terminal output** in your reply.
4. Only then describe or quote the function.

Previous versions of this design failed three times in a row for the same reason. Index and geometry arithmetic was written but never executed. Never state a number you did not compute in this session. If you estimate something, label it **ESTIMATE**.

## 1. Fixed inputs

| Item | Value |
|---|---|
| Instrument | XAUUSD, H1 bars |
| In-sample data | `data/raw/<FILL IN file name>.csv`, 2005-06 → 2025-12, has bid and ask columns |
| Holdout data | `data/holdout/<FILL IN>.csv`, 2026-01 → 2026-10. **Do not open it** until Step 7 allows it |
| Account size for risk checks | `ACCOUNT_USD = <FILL IN>` |
| Lot size | 0.01 (broker minimum; 1.00 lot = 100 oz, so $1 move = $1 at 0.01 lot) |
| Broker / platform | MT5, **hedging** account, `<FILL IN broker>`, server time zone `<FILL IN>` |

Eras (`data/eras.yaml`):

| Era | Window | Gold (approx.) | Character |
|---|---|---|---|
| A | 2005-06 → 2011-08 | 430 → 1,900 | strong uptrend, wide spread vs ATR |
| B | 2011-09 → 2015-12 | 1,900 → 1,050 | strong **down**trend |
| C | 2016-01 → 2020-12 | 1,060 → 1,900 | uptrend |
| D | 2021-01 → 2025-12 | 1,800 → 4,000 | strong uptrend |

Every era gets a 100-bar warm-up taken from the preceding data. Warm-up bars are never traded.

## 2. Already done — do not rewrite

`signals/aroon.py` and `tests/test_aroon.py` exist. All 19 tests pass, and a mutation check confirmed they fail on the earlier index bug and on swapped tie rules. Treat this file as the contract:

- Arrays run oldest → newest; `end` = index of the last **closed** bar.
- `bars_back` = 0 for the newest bar. Aroon Up = 100 × (70 − bars_back) / 70 → **100.0 fresh, 1.43 at 69 back**.
- `ties` ∈ {`newest`, `oldest`, `average`}; anything else raises `ValueError`.
- Use `aroon_osc_series()` in the engine. It matches the scalar version bar for bar (test T15).
- `tests/test_aroon.py` uses `l` for "low", which Ruff flags as E741. Do not edit the file; add a per-file ignore (`"goldnix/tests/test_aroon.py" = ["E741"]` under `[tool.ruff.lint.per-file-ignores]`).
- Load every YAML config with a strict loader that rejects bare `on`/`off`/`yes`/`no`, and test that `decision.yaml` round-trips to the expected Python values.

## 3. Repository layout

```text
goldnix/
  data/raw/  data/clean/  data/holdout/  data/eras.yaml
  signals/        aroon.py (done), crosses.py
  ingest/         ingest.py, segments.py, gaps.py
  params/         atr.py, decision.yaml, variants/*.yaml
  sim/            engine.py, policy.py, baseline.py
  metrics/        report.py, bootstrap.py, montecarlo.py
  gates/          rules.yaml, verdict.py
  parity/         atr_parity.py, ea_parity.py
  ea/             AroonBreakout.mq5
  tests/          one test file per module
  out/run_<hash>/ config.yaml, data_hash.txt, trades.csv, metrics.json, verdict.md
```

**Never name a package `signal`.** It shadows Python's standard-library `signal` module and breaks asyncio and multiprocessing. Use `signals`.

## 4. Conventions used everywhere

- **Time:** all timestamps are UTC-aware. Convert broker server time with an explicit DST table, never a fixed offset.
- **Bar indexing:** the signal is evaluated on closed bar `t`; entry is at `open[t+1]`. No other offsets anywhere.
- **Prices:**
  - Mid = (bid + ask) / 2.
  - A BUY fills at the ask; its stop and target are checked against the bid. A SELL is the mirror.
  - This charges **exactly one spread per round trip**. An added layer pays its own spread.
- **R:**
  - 1R = the stop distance of a single-layer trade = 1.0 × ATR at entry, **excluding spread**.
  - Basket results are expressed in that same R.
- **ATR:** period 14 on H1, the value at signal bar `t`, **frozen at entry**. Whether it is a simple average or Wilder smoothing is decided by the parity harness (step 2).

## 5. Pre-declared decision config (`params/decision.yaml`)

Freeze this before step 4 starts. Only this config is gated. Every other setting is sensitivity, reported and never gated. **No variant may be promoted to the decision config without new data.**

```yaml
aroon_period: 70
threshold: 50
ties: newest
volume_filter: none            # vf_none
vol_ceiling_atr: 0.30          # skip signal if spread_at_signal > 0.30 * ATR
news_filter: false             # never write bare off/on/yes/no: YAML 1.1 reads them as booleans
stop_atr: 1.0
target_atr: 2.0
min_distance_usd: 0.50         # floor for stop distance
max_layers: 1
trailing: false
one_position: true             # opposite signal while open is ignored
session_filter: none
friday_no_entry_from_utc: "19:00"
friday_flat_utc: "20:00"
daily_halt_r: -2.0             # realised R per UTC calendar day
holiday_exclusion: true        # Dec 24-26, Jan 1, Good Friday, US Thanksgiving
fill_policy: stop_first
gap_policy: adverse_at_open_favourable_at_target
```

Sensitivity variants (reported only), each changing **one** item:

- `ties`: oldest, average
- `vol_ceiling_atr`: 0.25, 0.40
- `fill_policy`: target_first
- `gap_policy`: both at open
- spread × 1.5 and × 2.0
- spread = 0, to separate "no edge" from "spread ate the edge"
- `vf_low_abs`: keep a SELL only if volume < 1.5 × trailing-1,000-bar median. This is a **new idea**, not a GOLDNIX stand-in.
- `news_on`: only if a calendar back to 2005 is sourced
- `layer`: `max_layers: 2`, `layer_atr: 0.5`, `basket_offset_atr: 1.0`, equal lots

Layer reference numbers, spread excluded:

- Once layered, the basket breaks even at entry − 0.25 ATR, and its target is entry + 0.75 ATR.
- Layered win = **+2.0R**, layered loss = **−1.5R**, basket break-even win rate = **42.9%**.
- With zero edge, the layered system's overall win rate is 42.9%, versus 33.3% for a single layer.
- Basket profit = total lots × offset.

## 6. Build steps

Do them in order. Stop at the end of each step, paste the outputs, and wait for approval.

### Step 1 — `signals/crosses.py`

- `BUY  = osc[t-1] < +50 and osc[t] > +50`
- `SELL = osc[t-1] > -50 and osc[t] < -50`
- Both use closed bars only.

Tests: synthetic series with known crossing bars, the exact-threshold case (`osc == 50` is not a cross), and no signal before the first valid Aroon bar.

### Step 2 — Data layer

**`ingest.py`.** Parse to UTC, drop duplicates, sort, and check monotonic time.

**First output, before anything else:** the distribution of `ask − bid` per year (min, p5, median, p95, max, share of rows equal to the modal value).

- If the spread is essentially constant (for example always 0.41), the ask is **synthetic**. Print the warning: *"Spread is synthetic. The vol ceiling is a volatility filter, not a spread filter. Live spread spikes are NOT modelled; rely on spread × 1.5 / × 2 stress."*
- Flag rows with `spread <= 0` or `spread > 1.00`.

**`gaps.py`.** Record every gap longer than 4 hours inside a session, or longer than 60 hours over a weekend, to `clean/gaps.csv`. Tag a trade `gap_risk` if it was open across any recorded gap.

**`segments.py`** (volume units). For each candidate bar, compare the median volume of the 500 bars **before** it with the 500 bars **after** it. Mark a unit change where the ratio is greater than 5× or less than 0.2×, and holds for 50 bars. Do not compare to a global median: it sits between the two segments and hides the step. Volume-dependent variants never span a boundary.

**Holidays** are excluded from trade generation but kept for warm-up.

**`parity/atr_parity.py`.** Compute ATR(14) both as a simple average of true range and with Wilder smoothing.

- The user exports about 200 H1 bars of MT5's `iATR(14)` values from their broker (write the small MQL5 export script for them).
- Pick the method whose maximum absolute difference is under $0.01.
- **Until parity passes, every result is labelled PROVISIONAL and no verdict is issued.**
- Bar boundaries come from the server-time offset; check that they line up.

### Step 3 — `sim/engine.py` and `sim/policy.py`

Bar-by-bar, one position, states `FLAT → OPEN → CLOSED`.

- **Entry:** at `open[t+1]` on the correct side of the spread.
- **Same bar touches both stop and target:** `stop_first` (decision) or `target_first` (sensitivity).
- **Gaps:** if a bar opens beyond the stop, fill at the open (adverse). If it opens beyond the target, fill at the target (favourable, conservative).
- **Order of checks for each new bar:**
  1. halts
  2. Friday flat
  3. holiday
  4. vol ceiling
  5. signal
- `trades.csv` columns: `era, entry_ts, exit_ts, dir, layers, entry, exit, stop, target, atr, spread_paid, r_multiple, mae_r, mfe_r, exit_reason, flags`.
- Count and report `skipped_by_vol_ceiling` **as a share of signals**, per era.

Tests (hand-computed): a long that hits the target; a long that hits the stop; a same-bar touch under both fill policies; an adverse gap through the stop; a favourable gap through the target; the Friday flat close; the daily halt; an opposite signal ignored while a position is open; a holiday bar skipped.

Also run: **stop-first vs target-first win-rate delta per era.** In a fat-tailed simulation, a stop and target both touched within one H1 bar happened in under 1% of trades (**ESTIMATE**; real gold news spikes add some). If the delta is more than 8 percentage points in any era, that era needs M1 data and the verdict for it is **NEEDS M1**.

### Step 4 — All four eras plus baseline, decision config only → DECISION POINT

**`sim/baseline.py`:**

- Random entries, uniform over **eligible** bars (the same filters as the signal).
- Per era, use the **same number of longs and the same number of shorts** as the signal run.
- Use the same exits and envelope.
- Run 200 independent draws; the baseline mean R is the average across draws.
- Report longs and shorts separately.

This exists because gold rose from about $430 to about $4,000. A 2:1 long system passes on drift alone. Era B, the downtrend, is where drift runs the other way and long and short results should flip if the edge is only beta.

Print per era and pooled: baskets, win rate, mean R, signal − baseline, long vs short split, skip share, `gap_risk` share.

**Stop here and report. Do not continue to step 5 without approval.**

### Step 5 — Sensitivity variants (reported only)

Run every variant from section 5. Present them as a table of deltas against the decision config. Nothing in this table can change the verdict.

### Step 6 — `metrics/` and `gates/` → verdict → FREEZE

**Bootstrap.** Block bootstrap with blocks of one calendar month and 10,000 resamples. Bounds are **one-sided, 5% tail**. Do not predict the bootstrap SE; report what it is.

**Gates (`gates/rules.yaml`), all on the pooled decision-config result:**

| # | Gate | Pass if |
|---|---|---|
| G1 | Block-bootstrap lower bound of mean R | > 0 |
| G2 | Signal − baseline, point estimate | ≥ +0.10R |
| G3 | Signal − baseline, lower bound | > 0 |
| G4 | Consistency | mean R > 0 in ≥ 3 of 4 eras |
| G5 | Pooled baskets | ≥ 1,000 — otherwise the verdict is **INSUFFICIENT DATA**, not FAIL |
| G6 | `gap_risk` share | ≤ 10% |
| G7 | Monte Carlo p99 of max drawdown **over one year of trades** (trades per year = observed rate), in $ at 0.01 lot | ≤ 12% of `ACCOUNT_USD` — otherwise **NOT TRADEABLE AT THIS ACCOUNT SIZE**, because 0.01 lot cannot be reduced |
| G8 | Stop-first vs target-first delta | ≤ 8 pp in every era — otherwise **NEEDS M1** |
| G9 | ATR parity | passed |

**Report but don't gate:** per-era bounds, win rate, longest losing streak, MAE, MFE, time in market, spread paid.

**Reference values for the report** (flat $0.41 spread, R excludes spread):

- Break-even win rate = (stop + spread) / (3 × stop).
- Win rate needed for +0.15R = (1.15 × stop + spread) / (3 × stop).
- Use the **actual** per-era ATR and spread, and recompute both formulas in code. The table below was computed with assumed ATRs, so it is only a sanity check:

| Era | Assumed ATR | Break-even WR | WR for +0.15R |
|---|---:|---:|---:|
| A | 1.60 | 41.9% | 46.9% |
| B | 2.40 | 39.0% | 44.0% |
| C | 1.80 | 40.9% | 45.9% |
| D | 4.00 | 36.8% | 41.8% |

**Freeze:** write `out/FROZEN.yaml` containing the decision config, its hash, the code commit and the in-sample verdict. After this, the decision config and the code are read-only.

### Step 7 — Holdout collapse check

- The code must **refuse** to read `data/holdout/` unless `out/FROZEN.yaml` exists and its hash matches the current config and code.
- Run once. No iteration.
- Segmentation medians and all normalisation statistics come from in-sample data only.
- Expect only about 40–70 baskets (**ESTIMATE**). This cannot confirm an edge; it can only catch a collapse.
- **Pass if:** holdout mean R ≥ in-sample mean R − 2 × √(SE_in² + SE_hold²)
  - SE_in = in-sample block-bootstrap SE
  - SE_hold = holdout SD of R / √n_hold
  - Using SE_in alone would wrongly fail a real edge 17–32% of the time.
- **If it fails: discard. Do not re-tune.**

### Step 8 — MQL5 EA and parity test (only if steps 6 and 7 pass)

`ea/AroonBreakout.mq5`. Inputs must mirror `decision.yaml` one-for-one:

```mql5
input double RiskLot        = 0.01;
input int    AroonPeriod    = 70;
input double Threshold      = 50.0;
input int    ATRPeriod      = 14;      // an int, not "ATRMult"
input double StopATR        = 1.00;
input double TargetATR      = 2.00;
input double LayerATR       = 0.50;    // must be < StopATR
input int    MaxLayers      = 1;
input double BasketOffsetATR= 1.00;
input double VolCeilingATR  = 0.30;
input double DailyHaltR     = 2.0;
input double DDHaltUSD      = 0;       // set from the step-6 Monte Carlo p99
input int    FridayFlatUTC  = 20;
input int    FridayNoEntryUTC = 19;
enum TIES { TIES_NEWEST, TIES_OLDEST, TIES_AVERAGE };
input TIES   Ties           = TIES_NEWEST;
input ulong  Magic          = 20261108;
```

Requirements:

- `OnInit` rejects `_Period != PERIOD_H1`, rejects `LayerATR >= StopATR`, and rejects a netting account when `MaxLayers > 1`.
- **Aroon is computed with an explicit loop**, using the same bars-back and tie rule as `signals/aroon.py`. Do not rely on `iHighest` tie behaviour.
- ATR uses the method chosen by the parity harness. If `iATR` is used: it returns a handle, so read it with `CopyBuffer` at shift 1.
- **Every tick, outside the new-bar guard:**
  1. daily-halt check
  2. drawdown-halt check
  3. Friday flat close
  4. stop and target management
- **Once per new bar:** signal evaluation and entry.
- Convert server time to UTC with your own DST table. In the MT5 tester, `TimeGMT()` returns simulated server time, so it cannot be used.
- Persist the frozen ATR per ticket, `dailyR` and the halt flag in `GlobalVariables`, so a terminal restart does not lose them.
- No trailing stop. No martingale. No DLLs. No WebRequest.

**`parity/ea_parity.py`:**

1. Run the EA in the MT5 tester over a parity window.
2. Run the Python simulation **on the same broker history** exported from MT5, not on the CSV, so differences come from logic and not from data.
3. Diff the two trade lists.
4. Require at least 95% matching entries and exits (same bar, same direction, same exit reason), and list every mismatch.

### Step 9 — Forward demo

Run the EA on a **demo** account for at least 8 weeks. Compare it weekly with the simulation over the same period, and report spread skips, slippage and trade-list differences.

### Step 10 — Live

0.01 lot only, until 300 logged baskets. The risk envelope is enforced in code, not by memory.

## 7. Never do these

- Do not open the holdout before `FROZEN.yaml` exists.
- Do not change the decision config after step 4 starts.
- Do not re-tune after a failed gate. Record the failure.
- Do not raise or lower thresholds, ceilings or stops to make a gate pass.
- Do not edit a test's expected value to make it pass. A failing test means the code is wrong until proven otherwise.
- Do not call this a GOLDNIX proxy. GOLDNIX runs on M1 with a martingale grid; this is a new H1 strategy that borrows its entry signal.
- Do not describe any result as profitable. Describe it by its gates.

## 8. Reply format for every step

1. What was built (file list)
2. Test output, pasted verbatim
3. Results table(s)
4. Anything that surprised you or contradicts this prompt — **flag it; don't silently fix it**
5. The single next action, waiting for approval
