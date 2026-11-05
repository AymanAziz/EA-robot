# Data and ML verification performed locally

On 2026-11-05, the public Coinbase Exchange API actually returned **1,344 BTC/USD completed fifteen-minute candles**, covering opening timestamps 2026-10-22 04:30 UTC through 2026-11-05 04:15 UTC. No provider credentials were needed. Collection, timestamp/OHLCV validation, genuine LightGBM fitting, disjoint calibration, walk-forward evaluation, native artifact persistence and two exactly equal saved-model backtests completed successfully.

The candidate **failed validation and was left inactive**. Failure reasons included insufficient qualifying validation/test trades, lack of positive net validation/test returns, failure to outperform the capped buy-and-hold benchmark, nonpositive Sharpe, Brier worse than class prior, no positive lower bootstrap mean P/L, and insufficient profitable walk-forward folds. This check provides no evidence of profitability. No broker order was submitted and no production active-model pointer was created.

Local, ignored artifacts are in `var/verification/`: `btc_14d.csv`, `data_ml_verification.json`, and isolated `models/`. They are generated evidence rather than repository fixtures; back them up if needed. After the final session-horizon risk update, the genuine data was retrained and backtested again as candidate `20261105T041500-53cea60a1520`, with policy SHA-256 `c48a67d47d35a5395b037be6b9e4bde13df146aad7428787e31c5a22d48f8778`. Policy/source changes intentionally invalidate that candidate until retrained; final metadata is the authoritative record.

The explicitly enabled public-feed integration test also actually passed:

```sh
PT_RUN_PUBLIC_DATA_INTEGRATION=1 .venv/bin/python -m pytest tests/integration/test_public_data.py -q
```

That check collected twelve recent completed Coinbase candles and a real timestamped bid/ask quote. It **does not verify Alpaca Paper or OANDA Practice account access, eligibility, order submission, fills, or reconciliation**. Those remain separate credential-gated checks.

The 33 focused local tests in `test_data.py`, `test_ml.py`, and `test_backtest.py` passed. They include deterministic, explicitly artificial ML fixtures: one fixture tests genuine candidate rejection; another predictable price-cycle fixture genuinely passes the configured gates and verifies promotion, calibrated native-model inference, expiration, and invalidation after policy/cost changes. These artificial results are tests of application behavior and are never represented as financial-market results. Other tests cover no feature leakage, next-open labels, completed bars only, provider failure, duplicate/gapped history, calendar closures, costs, gap stops, missing edge, expected-return exits, exposure sizing, session-horizon admission, immutable candidate versions and reproducibility. Together with the risk tests, 53 local tests passed. `ruff check` passed for these modules/tests.

## Policy alignment audit

The backtest now calls the operational `decide()` and `approve_entry()` functions. It shares threshold, cost, regime, liquidity, no-averaging, capped-capital sizing, exposure limits, volume participation, daily and drawdown circuits, stops/targets and expected-return exit semantics. Its maximum holding period is four fifteen-minute bars, which the operational engine must monitor even when a model becomes unavailable.

Historical validation still estimates bid/ask from an explicit spread assumption and assumes next-bar-open execution. Production runs start seconds after candle completion, and real paper fills or minute-by-minute software stops may differ. Each model's backtest is isolated; the production portfolio risk engine may additionally reject trades across combined broker/correlation exposure. These limits are recorded in candidate metadata and [the research contract](DATA_ML_SOURCES.md).
