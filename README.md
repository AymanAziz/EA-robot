# Papertrade

A Python platform for measuring and automatically executing **paper-only** trading strategies across BTC/USD, ETH/USD, SPY, QQQ, EUR/USD and GBP/USD. It combines completed 15-minute candles, per-symbol calibrated LightGBM models, optional Groq/Nous Hermes reasoning, validated signal fusion, independent portfolio risk limits, persistent reconciliation, a FastAPI backend and an authenticated Streamlit dashboard.

Live trading is blocked by configuration and hardcoded paper broker endpoints. The default execution venue is a persistent local simulator using real market quotes. It is clearly separate from Alpaca Paper and OANDA Practice. No trained model, no validated edge, unavailable credentials or stale data means **NO TRADE**. Training never automatically activates a model.

The cloud layout is **Streamlit Community Cloud for the dashboard, Oracle Always Free VM for the engine/API/SQLite and AI worker**. Community Cloud never holds broker or AI credentials, runs the scheduler, or owns trading history. See [Streamlit Cloud setup](docs/STREAMLIT_CLOUD.md). No large local language model or GPU is required.

The upgrade preserves existing data and paper execution. **Cloud AI and new strategy execution default OFF.** Explicitly enable an independently validated quant strategy before entries resume. AI-dependent execution additionally needs a current approved validation certificate; missing AI defaults to HOLD without switching providers. Protective exits and reconciliation continue independently.

## Requirements

- Python 3.12+; Python 3.12 is the deployment target.
- CPU only. LightGBM needs an OpenMP runtime: `brew install libomp` on macOS; `sudo apt-get install libgomp1` on Ubuntu.
- Internet for real market data. Optional Alpaca paper credentials and an eligible, USD-denominated OANDA Practice account. Country/account eligibility and free data entitlements are provider decisions.
- SQLite state on a local filesystem. Never put the WAL database on NFS or mount it on multiple machines.

On macOS with Homebrew, install the runtime with `brew install python@3.12 libomp` if Python 3.12+ is not already available. The system Python on older macOS releases can be too old.

## Install and configure

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.lock.txt
python -m pip install --no-deps -e .
python scripts/configure_env.py
papertrade init-db
```

`scripts/configure_env.py` creates `.env`, asks for a dashboard password, stores an Argon2 hash and generates a random backend token. It sets file permissions to `0600` and never prints secrets. Edit `.env` privately. Keep `PT_MODE=paper` in every environment.

For an unattended local setup, `python scripts/configure_env.py --generate` writes a random initial password to `var/initial-admin-password.txt` with mode `0600`. Sign in as `admin`, save the password securely, and remove that file. It is ignored by Git.

Use a separate database and state directory for each execution venue and paper account. When switching to broker paper execution, set `PT_EXECUTION=brokers`, `PT_STATE_DIR=var/brokers`, and `PT_DATABASE_URL=sqlite:///var/brokers/papertrade.db`, then run `papertrade init-db` and collect/train against that provider. The engine refuses account changes or mixed-provider candle history in existing state. These guards preserve portfolio and model provenance.

For Alpaca Paper, set `PT_ALPACA_KEY` and `PT_ALPACA_SECRET` from the **paper** account. For OANDA, set `PT_OANDA_TOKEN` and `PT_OANDA_ACCOUNT_ID` from **Practice**. Never paste real credentials into a source file or shell command. `PT_EXECUTION=brokers` selects broker-hosted paper execution; `simulator` keeps fills local. A provider outage disables affected execution and records the reason; it never silently turns broker orders into simulated fills.

```bash
papertrade verify-brokers
```

This is a read-only credential/connectivity check. It is not an order-execution certification.

## Collect, train and evaluate

Quote symbols containing `/`. Use UTC ISO timestamps. Public crypto history is available without brokerage credentials; equities and forex require their configured data provider. Collect enough history for the chronological train/calibration/validation/test partitions and walk-forward windows.

```bash
PT_HISTORY_START="$(python -c 'from datetime import datetime,timedelta,timezone; print((datetime.now(timezone.utc)-timedelta(days=90)).isoformat())')"
PT_HISTORY_END="$(python -c 'from datetime import datetime,timezone; print(datetime.now(timezone.utc).isoformat())')"
papertrade collect 'BTC/USD' --start "$PT_HISTORY_START" --end "$PT_HISTORY_END"
papertrade train 'BTC/USD'
```

Training prints a version and its validation report. Review the chronological test results, turnover, transaction costs, rule baseline, buy-and-hold benchmark and walk-forward consistency. The acceptance report uses the held-out period; repeatedly tuning against it consumes that holdout, so reserve new subsequent data for an independent later evaluation. Replace `VERSION_FROM_TRAINING` with that exact version:

```bash
papertrade backtest 'BTC/USD' --model VERSION_FROM_TRAINING
papertrade promote 'BTC/USD' VERSION_FROM_TRAINING
```

Promotion refuses candidates that fail the explicit validation criteria. A model can fail, and no model is active initially. Each symbol has a separate artifact and validation decision. Collect and train the other instruments using the same commands. Source differences, limited free feeds, survivorship bias and realistic execution assumptions are documented in [ARCHITECTURE.md](ARCHITECTURE.md) and the saved model report. Synthetic data appears only in unit-test fixtures; it is never used to claim an investment result.

## Configure cloud AI and strategy validation

On the **Oracle VM**, privately configure the selected provider key and verify its actual billing plan. Groq is the default adapter; its model ID must be selected from the account-visible catalog. Neither a model ID nor a free entitlement is assumed. Hermes is optional paid access and is never selected automatically. Keep `PT_AI_FALLBACK_PROVIDER=none` and `PT_AI_ALLOW_PAID=false` unless paid usage is explicitly authorized.

```bash
papertrade ai-models --provider groq
papertrade ai-status
```

Set `PT_GROQ_MODEL` to the exact supported catalog ID and, after confirming a free Groq account, set `PT_AI_ACCOUNT_TIER=free` and `PT_AI_ENABLED=true`. Account plan declaration is an operator assertion; the API cannot enforce a free-only billing switch. Local request/token budgets limit the application and do not guarantee provider allowances. See [AI setup and cost controls](docs/AI_SETUP.md) for all settings and troubleshooting.

```bash
papertrade run-once
papertrade analyze-ai
papertrade ai-status
papertrade compare-strategies 'BTC/USD'
```

The AI worker reads genuine stored candles/predictions, runs outside the execution lock, caches valid unchanged context and normally analyzes hourly. Its timer checks the frequency/event gates every quarter-hour. Context explicitly states when verified news/macro data is absent. AI output is strictly validated untrusted data, and its confidence is an uncalibrated opinion.

Comparison uses timestamped forward observations and estimated execution, labels that source, and can reject every strategy. It cannot invent historical AI opinions or turn a recommendation into a broker fill. For `ai_filtered_quant` or `hybrid`, review a passing comparison and explicitly approve its stored validation ID:

```bash
papertrade approve-strategy VALIDATION_ID_FROM_COMPARISON
```

Failed/expired/incompatible certificates cannot authorize execution. Quant-only requires its independently accepted/promoted model and explicit `PT_STRATEGY=quant_only`, `PT_STRATEGY_EXECUTION_ENABLED=true`; AI-filtered/hybrid require their corresponding validated strategy and the same explicit execution flag. `ai_only_research` always forbids automatic execution. These are configuration/strategy activation steps, not per-paper-order approvals. Once activated, supported BUY and SELL/CLOSE orders remain automatic and risk-controlled.

## Start locally

Run the backend and dashboard in separate terminals with the virtual environment activated:

```bash
papertrade serve
```

```bash
papertrade dashboard
```

Open <http://127.0.0.1:8501> and sign in with the configured username and password. FastAPI stays on <http://127.0.0.1:8000>. The dashboard reads stored records through authenticated backend routes; it does not generate demonstration metrics or write SQLite directly.

Run one analysis and inspect its result:

```bash
papertrade run-once
papertrade status
```

Start unattended local paper operation:

```bash
papertrade scheduler
```

APScheduler analyzes at minutes `00,15,30,45`, twenty seconds after candle close, runs the protective monitor each minute at second 10, and checks AI frequency/event gates after quant cycles at second 40. AI HTTP work uses a separate lock and cannot authorize a broker order. Use either this process **or** the supplied systemd timers. Never run both scheduling mechanisms against the same deployment. Local automatic operation requires this process and machine to stay running; use the server deployment to operate while the laptop is off.

## Controls, logs and safe stop

```bash
papertrade control pause
papertrade control resume
papertrade control kill
papertrade control close_all
papertrade status
```

The dashboard exposes the same authenticated controls and market enable/disable controls. Pause blocks new entries while reconciliation and protection continue. Emergency stop is persistent and blocks entries. A persistent 60-minute maximum holding period also triggers an exit independently of the ML model. Close-all requests reductions; it does not claim liquidation until confirmed fills and positions are reconciled. Unknown submissions are queried by their original client ID and are never blindly retried.

For an ordinary safe shutdown, pause entries, close paper positions if desired, confirm orders/positions, then stop the scheduler. A process stop alone cannot cancel an already accepted broker order or guarantee an exit while a market/provider is unavailable. See the full incident runbook in [DEPLOYMENT.md](DEPLOYMENT.md).

JSON logs go to stdout/stderr; the database records runs, health, risk events and audit records. On the server:

```bash
sudo journalctl -u papertrade-engine.service -u papertrade-monitor.service -u papertrade-ai.service -f -o cat
sudo journalctl -u papertrade-api.service -u papertrade-dashboard.service --since today
```

## Tests and security checks

```bash
python -m pytest -q
python -m ruff check src tests
python -m pip_audit
```

Default tests use temporary SQLite files, deterministic synthetic research fixtures and mocked external responses. Real-paper integration tests are skipped unless explicitly enabled:

```bash
PT_RUN_PAPER_INTEGRATION=true python -m pytest tests/integration -m integration -v
```

These integration tests are read-only: they check real paper account state and completed market data, and never submit an order. Credentials and network/provider eligibility are required. Order submission/rejection/reconciliation are tested with mocked provider responses; an actual broker-hosted execution cycle still requires configured credentials and a validated active model. A skipped test or a mocked HTTP response is not a successful broker-hosted integration test. Dependency audit findings must be reviewed against the installed environment before exposure.

## Server deployment and cost

Run on Oracle Always Free ARM64 Ubuntu using [DEPLOYMENT.md](DEPLOYMENT.md), and host the frontend on [Streamlit Community Cloud](docs/STREAMLIT_CLOUD.md). The installer, hardened systemd services, 15-minute quant/AI-gate timers, independent minute monitor, Caddy HTTPS templates, optional Compose setup and SQLite backup tool are included. A paid AI subscription, GPU, Telegram, hosted database or premium data feed is not required by the default configuration. Optional paid access remains disabled.

RM0/month is a resource target, not a billing guarantee. Select resources marked Always Free in the home region, watch tenancy quotas, storage and network usage, and avoid paid upgrades/add-ons. Capacity can be unavailable and idle instances can be reclaimed. The current published [Oracle Always Free documentation](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm) is the authority for allowances. An external heartbeat monitor detects loss of the entire host; an internal web page cannot do that.

Read [ARCHITECTURE.md](ARCHITECTURE.md) for design and failure modes, [DEPLOYMENT.md](DEPLOYMENT.md) for installation/recovery, [SECURITY.md](SECURITY.md) for threat controls and [docs/DEPLOYMENT_SOURCES.md](docs/DEPLOYMENT_SOURCES.md) for official deployment references. Paper results do not establish profitability or reproduce real execution quality.

The implementation's actual local checks and external verification gaps are recorded in [docs/VERIFICATION.md](docs/VERIFICATION.md).

The in-place cloud AI upgrade, preserved history, latest test results and deployment gaps are recorded in [docs/AI_UPGRADE_VERIFICATION.md](docs/AI_UPGRADE_VERIFICATION.md).
