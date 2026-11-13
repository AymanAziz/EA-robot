# P01 independent replay and qualification evidence

This package verifies the existing M1 channel20 EA with profit protection.
It does not claim a profitable strategy or a completed Step 1–8 qualification.
The current assessment is `REPORT.md`; the declaration remains
`../goldnix_auto_m1/protection_protocol.json`. G1–G9 are unchanged.

## Public boundaries

- `data.read_ticks` / `minute_bars`: executable Bid/Ask chronology, separately
  aggregated extrema and completed-bar availability. Missing quotes stay missing.
- `download_candles.decode` / `candle_audit.pair`: separate public daily M1 format,
  checked hashes and explicit placeholder classifications. Candles cannot replace
  the intraminute quote path needed by profit protection.
- `policy.plan_protection`: independently expressed arithmetic from the declared
  rule, without importing the production MQL planner.
- `engine.Broker`: quote-side fills and server stops before timer management;
  monotonic profit protection, explicit costs, rounding and favourable-gap policy.
- `replay.replay`: completed M1 signals, staged warmup/resync, one position,
  quote freshness, seven attempts, Malaysia risk-day rollover, −2R entry halt,
  10 USC equity guard, session/Friday closes and one-second management.
  Native signal decisions, entries, exits and readiness flags are not inputs.
- `parity.analyse`: outer-joined actual trades and every normal entry decision,
  with unmatched trades counted against the denominator. Requires exact prices,
  direction, entry time, whole exit second and reason, exceeding M1 bar matching.

## Evidence and calibration decisions

Three native runs are preserved under `out/`. The February 1–2 smoke run overlaps
the complete February run and must not be added to its trade population.
January and February 2024 are disjoint engineering windows. Both lie within the
predeclared in-sample years; neither is a fresh holdout.

The adapter generates a tester-only copy of the production EA. It changes the
identity guard, file namespace, clock/account wrappers and callback names;
production entry and protection code are copied unchanged, with replacement
anchors and hashes retained. Real chart execution is rejected. Orders in these
runs are simulated. Live demo files and risk budgets are separate.

Measured timer timestamps advance every second even between stale quotes.
The replay derives warmup and recovery availability independently. An extra
causality audit removes all future observations and compares earlier decisions.

The initial independent SELL-stop comparison exposed a decimal equality error;
the broker comparator now uses a millionth of one tick for grid equality. A
regression test reproduces that failure. February initially matched96/99 exact
prices: three targets received favourable quote-price fills from MT5. That
initial result is preserved. `target_fill='quote'` now explicitly models the
observed native execution convention; the conservative research default remains
`target_fill='level'`. January verifies that convention on a separate window.
No entry/protection threshold was fitted or changed.

The USD 20 native account rounds money to0.01 USD, equivalent to1 USC. Real cent
accounts settle more finely. The engineering reference explicitly uses that
coarse precision; sensitivity diagnostics separately use0.01 USC. Native cash
figures must not be presented as exact cent-account predictions. Nonzero native
commission, swap or fees cause parity analysis to stop pending a cost model.

## Limits that still prevent formal qualification

- Generated tester ticks are not independently verified real historical ticks.
- The acquisition worker currently collects daily M1 candles only. Complete
  required exposure ticks, missing-window accounting and four-era metadata are
  still needed. No M5 interpolation or invented intraminute paths are used.
- The native launcher accepts only verified winter-offset windows. It rejects
  summer/DST-crossing requests instead of applying UTC+2 to summer history.
- The complete four-era200-draw matched random baseline has not been run or
  certified for the P01 account-dependent envelope. Older strategy baselines
  cannot be borrowed. The protection-off comparison is an ablation, not G2.
- Native parity covers normal modeled fills. Broker rejection/restart behavior
  remains covered by the separate production-manager fixtures from the earlier
  deployment, not by an invented historical rejection model.
- Tick/timer exports have no cross-stream sequence identifier for ambiguous
  equal-millisecond callback ordering. The checked generated archives have no
  duplicate tick timestamps; additional real-tick qualification must resolve
  that ambiguity rather than assume away source ordering.
- The prior2026 holdout was consumed. No qualifying P01 performance freeze or
  new untouched holdout exists. The code snapshot is not a Step 6 freeze.

## Reproduce

Run from the repository root:

```sh
PYTHONPATH=goldnix:. .venv/bin/pytest -q goldnix_p01/tests
PYTHONPATH=goldnix:. .venv/bin/python -m goldnix_p01.parity goldnix_p01/out/P01N_20261113T062543Z
PYTHONPATH=goldnix:. .venv/bin/python -m goldnix_p01.parity goldnix_p01/out/P01N_20261113T062008Z
PYTHONPATH=goldnix:. .venv/bin/python -m goldnix_p01.diagnostics goldnix_p01/out/P01N_20261113T062008Z
PYTHONPATH=goldnix:. .venv/bin/python -m goldnix_p01.candle_audit
```

`native_run` requires a fresh verified flat demo before terminal handoff, saves
private settings under ignored `var/`, disables chart trading during testing,
and restores the normal app in `finally`. It never restores an older risk
checkpoint. Capture-only chart activity may advance `sequence`/`last_signal`;
account ownership, attempts, risk budgets and pending exposure must remain intact.

The resumable data worker is `python -m goldnix_p01.download_candles` with
`PYTHONPATH=goldnix:.`. A process lock prevents duplicate collectors. It uses
serial requests separated by at least1.5 seconds by default, preserves raw hashes,
refuses2026 data and stops on the first transport/HTTP/validation failure without
automatic retries. Status and logs are in `var/goldnix_p01_m1/`. A stopped worker
is not an active downloader; inspect `PROGRESS.json` and the process receipt.
It does not automatically qualify data, access holdout or change the EA.
