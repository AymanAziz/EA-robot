# Step 7: one-time holdout collapse check

The Step 7 runner is implemented separately from the frozen strategy and Step 6
source trees. It reuses their original indicators and execution engine. It does
not change either decision configuration or the Step 6 verdicts. The public
boundaries tested are the specified collapse criterion and the freeze-gated,
single-use runner, including its input validation and output artifacts.

## Status and missing input

Prepared on 2026-11-12. No real holdout evaluation has run. Both corrected
Step 6 freezes and the original V1 freeze verify. The available local dataset
ends in December 2025. An unauthenticated HEAD request to the original provider's
2026 annual endpoint returned HTTP 401. Only response headers were requested;
no holdout price data was downloaded.

The [EV Trading Labs catalogue](https://evtradelabs.com/data) requires a free
account for current-year data. Download **XAUUSD / H1 / 2026** through that
account and provide its local path. The runner accepts the native `.json.gz`
annual file, uncompressed JSON, or the bid/ask CSV contract documented in
`docs/XAUUSD_DATASET.md`. A different source is not silently substituted.
No login credentials belong in this repository.

## Protocol fixed before access

- Evaluate **both frozen V1 and V2**, together, once. The two diagnoses are
  reported separately; there is no winner selection or parameter search.
- Trade window: **2026-01-01 00:00 UTC inclusive to 2026-10-01 00:00 UTC exclusive**.
  January follows the end of the training data. September is the last full
  month before the October 8–November 10 prices already used for ATR parity.
  The native annual download can contain later bars; they are excluded from
  indicators, simulation, and statistics. Receiving that file still exposes
  its raw contents, so do not claim the remainder stays sealed.
- Warm up V1 using the last 100 in-sample H1 bars, V2 using its frozen 280 bars.
  Start flat and trade signals from the holdout only, as with Step 6 era
  boundaries. No warm-up trades enter the results. The unchanged engine closes
  any remaining trade at the last selected bar and reports that exit count.
- Both decision configs use no fitted volume segmentation or normalization.
  No medians, calibration values, or other parameters are fitted to the holdout.
  Ordinary causal Aroon/ATR values continue to update from closed price bars.
- Use the corrected Step 6 pooled mean R and **monthly block-bootstrap SE**.
  The holdout SE is sample SD (`ddof=1`) divided by the square root of basket
  count. Pass exactly when
  `mean_hold >= mean_in - 2 * sqrt(SE_in**2 + SE_hold**2)`.
- Zero or one basket produces `INSUFFICIENT_DATA`, never PASS. No additional
  basket-count gate is invented. Even a PASS with more baskets detects only
  absence of a collapse under this criterion, not evidence of a profitable edge.
- Failure produces `FAIL_DISCARD`: discard without retuning on these data.
  Step 8 requires both Step 6 and Step 7 to pass. The existing Step 6 failures
  therefore keep Step 8 unavailable regardless of this diagnostic.

Input validation rejects invalid prices, negative open/close spreads, invalid
OHLC, non-UTC or duplicate/unsorted/sub-hour timestamps, epoch mismatches, and
rows outside 2026. The selected interval must start/end within seven days of
its prescribed boundaries and have no gap over seven days. Those coverage
checks are fixed data-quality guards, not performance gates. No bars are
repaired, interpolated, or silently deduplicated. Smaller gaps remain visible
to the original gap handling. These checks do not independently authenticate
the provider or prove complete market coverage.

## Commands

From the repository root, verify without touching holdout prices:

```sh
PYTHONPATH=.:goldnix .venv/bin/python -m goldnix_step7.runner --preflight
```

Once the downloaded file exists, execute the single authorized attempt:

```sh
PYTHONPATH=.:goldnix .venv/bin/python -m goldnix_step7.runner \
  --holdout '/absolute/path/to/2026.json.gz'
```

Before the first holdout read, the runner verifies source/config/artifact hashes,
the in-sample data hashes and both corrected freezes. It then exclusively
creates `out/ATTEMPT.json`, recording the window, frozen inputs and Step 7 source
hashes. Missing input files or failed preflight checks do not consume a run.
Once access starts, the lock remains even if parsing, validation, simulation,
or reporting fails. There is no force/reset option. Do not remove the lock or
repeat an evaluation on these data. An interrupted attempt without a final
result is still consumed; inspect its artifacts before deciding what happened.

The original download is snapshotted read-only under the git-ignored
`var/goldnix_step7_holdout/`. `out/INPUT.json` records its hash. The result includes
trade CSVs and metrics for each strategy, `REPORT.md`, `RESULT.json`, artifact
hashes and runtime versions. A caught failure writes `ERROR.json`. Inputs and
code are checked again before a final result is written.

The inherited H1 fill model, spread treatment, broker/data-source differences,
and end-of-window marking remain research limitations. This does not place
orders or perform broker execution parity.

## Verification

```sh
PYTHONPATH=.:goldnix .venv/bin/pytest -q goldnix/tests goldnix_v2/tests \
  goldnix_step6/tests goldnix_checks/tests goldnix_step7/tests
.venv/bin/ruff check goldnix_step7
```

Tests use synthetic bid/ask bars in temporary directories. They do not open
real holdout data or consume the repository's one-time attempt.

Data attribution for an eventual evaluation: EV Trading Labs
(https://evtradelabs.com/data).
