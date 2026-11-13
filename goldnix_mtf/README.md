# User method: isolated Step 6 evaluation

The completed review is [out/U01_final_review/REPORT.md](out/U01_final_review/REPORT.md).
This candidate does **not** pass: G1–G5 fail, G6–G9 pass. The original gate
function returns `INSUFFICIENT_DATA` because 788 trades are below its 1,000-trade
minimum; profitability and edge gates fail independently.

The single registered candidate implements H1 direction, an M15 EMA pullback,
and an M5 break–retest–reclaim sequence, with symmetric BUY/SELL handling. Numeric
parameters were explicit starting assumptions. The existing demo and frozen
V1/V2 strategy files were preserved.

- [Frozen strategy protocol](protocol.json) and [registration](REGISTERED.json)
- [Final metrics](out/U01_final_review/RESULT.json)
- [Simulated trades](out/U01_step6_exit_day_corrected/trades.csv)
- [Setup decisions](out/U01_step6_exit_day_corrected/setup_decisions.csv.gz)
- [Native parity protocol](parity/PROTOCOL.json) and [latest export pointer](parity/LATEST.json)
- [Independent audit](out/verification/RECEIPT.json)

`out/U01_step6` preserves the initial attempt. The authoritative historical
calculation is `out/U01_step6_exit_day_corrected`: its stop-day accounting fix
is explained in [CORRECTION.json](CORRECTION.json). The strategy parameters,
registered trial count and statistical seeds did not change. The strategy's
788 trades were unchanged; baseline statistics changed slightly. The final
review supplements that immutable result with newly collected native M5 parity
evidence. Earlier reports correctly recorded G9 as unverified at their creation.

The first native H1 export lacked initialized history. A retry explicitly
requested the additional indicator history, keeping the declared 1,000 rows,
800-bar warmup, 200 comparison bars and strict 0.01 tolerance. Recent broker
prices served only this parity check; no recent strategy returns were evaluated.

Historical data: 21 public M5 annual files, 2005–2025, from
[EVTradingLabs](https://evtradelabs.com/data), which attributes underlying ticks
to Dukascopy. Local cache: `var/goldnix_mtf_m5`; archive hashes and validation
counts are saved with the result. The study is exploratory on previously
examined calendar history, not untouched validation.

The historical evaluator and finalizer refuse to overwrite completed outputs.
Do not delete freezes to rerun, optimize settings under this candidate ID, or
treat the failed result as authorization for new execution. A new research
variant requires its own disclosed registration and output directory.

Verification command:

```sh
PYTHONPATH=.:goldnix .venv/bin/pytest -q goldnix_mtf/tests \
  goldnix_step6/tests/test_baseline.py goldnix_step6/tests/test_bootstrap.py \
  goldnix/tests/test_montecarlo.py goldnix/tests/test_verdict.py
.venv/bin/ruff check goldnix_mtf
```

36 tests passed. Native parity passed for M5 ATR14, H1 EMA50, M15 EMA20,
400 higher-timeframe availability comparisons and complete OHLC aggregation.
These checks validate the implementation, not profitability or tick-level fills.
