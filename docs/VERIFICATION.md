# Implementation verification — 2026-11-05

This repository was implemented and exercised locally on macOS ARM64 with Python 3.12.16. The environment is **paper only**, using the persistent local simulator. There are no active models and no broker credentials. No external broker orders were submitted.

## Actually executed

| Check | Observed outcome |
|---|---|
| Dependency installation | Complete; exact versions in `requirements.lock.txt`; `pip check` passed |
| Alembic initialization/upgrades | All three migrations applied to the application database; `alembic check` reports no outstanding schema changes |
| Default automated tests | 123 passed, 3 skipped; external integrations are skipped by default |
| Ruff | Passed for application, tests and scripts |
| Dependency vulnerability audit | No known vulnerabilities found after upgrading filelock to 4.2.9 |
| Explicit public-data integration | Passed against Coinbase Exchange: real completed bars and bid/ask quote |
| Historical data | 1,344 real BTC/USD candles collected and stored; the CLI separately collected 96 real candles successfully |
| ML training | Actual CPU LightGBM training, calibration, chronological evaluation, walk-forward validation and native artifact persistence completed |
| Reproducibility | Two saved-model backtests on the real dataset were identical; CLI train/backtest also succeeded |
| Acceptance gate | The real-data candidate failed and remains inactive; no profitability claim |
| Running FastAPI | Actual HTTP health, authenticated login/status/tables and unauthenticated-control rejection verified |
| Emergency stop | Actual authenticated HTTP kill/resume persisted the flags and verified the paper state |
| Running Streamlit | Actual HTTP health returned 200; Streamlit AppTest also rendered login and authenticated views |
| Running automation | APScheduler started with quarter-hour analysis at second 20 and minute protection checks at second 10; a real analysis completed successfully |
| Actual analysis decisions | Crypto: HOLD for missing/invalid active models. Equities/forex: disabled for missing market-data credentials. Zero stored orders |

The mocked/simulator test cases cover risk sizing and global caps, correlations, daily loss/drawdown circuits, no averaging, stale/gapped/incomplete data, missing/expired models, inference, failed validation, order rejection and uncertainty, duplicate/restart handling, partial fills, hosted protective coverage, cancellation races, model-independent holding expiry, ledger migration, account/feed isolation, FIFO net P/L, authenticated controls, dashboard reads and consistent SQLite backups. Test fixtures with artificial predictable prices are explicitly synthetic and are never reported as investment results.

Local generated evidence lives under ignored `var/verification/`. See [VERIFICATION_DATA_ML.md](VERIFICATION_DATA_ML.md) for the real-data research details and limitations. The application database contains the rejected candidate and actual stored candles; it contains no active-model pointer or invented order history.

## Not externally verified

Alpaca Paper and OANDA Practice account eligibility, entitlements, connectivity, actual order submissions/fills and hosted reconciliation need the user's eligible paper account credentials. The two real broker tests are read-only and were skipped. Mocked HTTP contracts do not certify those integrations against an account.

Oracle ARM64 provisioning, Docker builds, systemd operation, Caddy certificates, firewall rules and external heartbeat delivery were not run on a cloud host. Deployment files and instructions are supplied; no cloud resources or spending were created. Local operation stops when this machine stops. Server deployment is needed to run independently of the laptop.

Upstream pandas/NumPy/calendar and FastAPI test-client deprecation warnings occur in the installed environment. They do not fail these checks; review them when updating the dependency lock. Passing application tests and a vulnerability audit do not establish strategy profitability or eliminate execution/outage risk.

## Local running state

Dashboard: `http://127.0.0.1:8501`. Backend: `http://127.0.0.1:8000`. Sign in as `admin`; the generated password is in `var/initial-admin-password.txt` with mode `0600`. Save it securely and remove that file. `.env` is private and Git-ignored.

The API, scheduler, constrained Caddy proxy, AC-power sleep assertion and verified daily backup are now supervised by per-user macOS LaunchAgents. `var/local-processes.json` records the core runtime labels; launchd logs are under `var/*-launchd.log` and are bounded by the backup job. Tailscale Funnel publishes the constrained proxy, while FastAPI remains loopback-only. LaunchAgents start after this user logs into macOS; the Mac must remain on AC power, awake with its lid open, and online. See [TAILSCALE_MACOS.md](TAILSCALE_MACOS.md). To stop new paper trading and request liquidation, use `.venv/bin/papertrade control kill`; keep monitoring running until broker positions and outstanding orders are confirmed closed. The full shutdown and recovery runbook is in [DEPLOYMENT.md](../DEPLOYMENT.md).
