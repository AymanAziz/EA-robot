# Updated Step 6 and Step 7

Run from the repository root:

```sh
PYTHONPATH=goldnix:. .venv/bin/python -m goldnix_p01.step67
PYTHONPATH=goldnix:. .venv/bin/pytest -q goldnix_p01/tests goldnix_step6/tests goldnix_step7/tests
```

Each run writes a new directory and records its location in `LATEST.json`.
Existing runs are preserved. `REPORT.md` is the current human-readable summary.

The runner authenticates the current production EA, protection headers,
independent replay and two existing native quote/timer archives. It replays
January and February 2024 with the declared conservative TP fill and 0.01 USC
settlement precision. It then runs 10,000 month-block bootstrap resamples and
100,000 one-year Monte Carlo paths with fixed seeds. Chunking limits memory use
and is tested against the existing Monte Carlo implementation.

Every G1–G9 result separates its **diagnostic threshold** from its **formal
qualification status**. Missing baseline, four-era coverage or execution
evidence remains unavailable. The runner cannot create a qualifying freeze.
The two available calendar blocks, generated quote paths, independent monthly
account resets and two-hour February coverage shortfall are explicit limits.

Step 7 runs a prerequisite audit only. It checks candidate identity, all nine
formal gates, source identity, freeze verification and the requested period
against consumption metadata. The current candidate has no qualifying freeze
or registered untouched period. Only the previous consumption receipt is read;
no holdout prices or new once-only attempt are accessed.

The output includes `PLAN.json`, `STEP6.json`, `STEP7.json`, `trades.csv`, source
snapshots and a checked artifact manifest. These snapshots preserve diagnostic
evidence; they are not performance freezes and cannot unlock holdout access.
