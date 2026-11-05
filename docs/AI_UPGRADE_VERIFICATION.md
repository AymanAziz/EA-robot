# AI upgrade verification — 2026-11-05

This is an extension of the existing application, not a rebuild. The gap analysis and minimal-change plan are in [AI_UPGRADE_GAP_ANALYSIS.md](AI_UPGRADE_GAP_ANALYSIS.md).

## Changes delivered

| Area | Files |
|---|---|
| Typed AI evidence, providers and accounting | `src/papertrade/ai/{schema,providers,budget,service}.py` |
| Conservative fusion and empirical comparison | `src/papertrade/ai/{fusion,evaluation}.py` |
| Existing execution integration | `src/papertrade/{engine,scheduler,cli,config,models,monitoring,logging}.py` |
| Actual backend resource observations | `src/papertrade/host_health.py` |
| Existing dashboard and Community Cloud frontend | `src/papertrade/dashboard.py`, `cloud_dashboard/streamlit_app.py`, frontend requirements/config/secrets example |
| Additive schema | `migrations/versions/17ad51897652_add_ai_analysis_budgets_and_strategy_.py` |
| Deployment | `deploy/papertrade-ai.service`, `deploy/papertrade-ai.timer`, `deploy/Caddyfile.api`, existing installer/docs extended |
| Configuration/security | `.env.example`, `.gitignore`, `pyproject.toml`, `requirements.lock.txt`, existing security/architecture/setup guides |
| Tests | Provider, service, durable budgets, fusion, comparison, engine integration, migration preservation and cloud dashboard tests added; original tests retained |

**One new backend dependency:** `psutil==7.2.2`. AI adapters reuse `httpx` and Pydantic. The Community Cloud frontend has a separate six-library dependency file and imports no broker, database, scheduler or ML execution module.

The migration adds `ai_analyses`, `ai_requests`, `strategy_observations` and `strategy_validations` with indexes and an observation uniqueness constraint. It does not drop or rewrite legacy trading tables. The existing environment file, account state, model artifacts, history and tests were preserved. The shared test fixture now explicitly opts into the previously tested quant execution behavior; fresh production settings default to execution authorization off.

## Checks actually run locally

- **245 tests passed; five opt-in external integration tests skipped.** Those skipped checks cover Alpaca, OANDA, public Coinbase and two AI model catalogs. Prior public Coinbase collection verification remains documented separately. No real AI connection or broker-hosted execution is inferred from mocks.
- `ruff check src tests scripts cloud_dashboard` passed; `pip check` passed; compilation and installer shell syntax passed.
- Alembic applied the additive migration to the existing application database; `alembic check` found no pending operations. A separate automated old-revision-to-head test preserved legacy rows.
- Dependency audit reported **no known vulnerabilities** for the installed Python environment.
- Existing quantitative source hashes still exactly match the hashes in the original persisted model metadata. Quant training, calibration, inference, risk and backtest regression tests continue to pass.
- A pre-upgrade SQLite backup was created under `var/pre-ai-upgrade-backups/`. At the preservation check, instruments stayed 6, model versions stayed 1, audit records stayed 6, and orders/fills/positions stayed 0. Candle count increased from 2,018 to 2,020 through genuine scheduled data collection. No history was removed.
- Actual restarted local FastAPI and Streamlit endpoints returned HTTP 200. Authenticated login and new AI table reads worked; unauthenticated reads returned 401. The actual status reported paper simulator mode, zero AI requests, no configured AI model, no positions, AI disabled and strategy execution disabled.
- Official PyPI metadata showed compatible CPython 3.12/Linux AArch64 wheels for all seven checked native dependencies. This checks availability, not execution on an Oracle VM. See [ARM64_COMPATIBILITY.md](ARM64_COMPATIBILITY.md).

Generated evidence is Git-ignored under `var/verification/`: `ai-upgrade-http-smoke.json`, `ai-upgrade-history-preservation.json`, `quant-source-preservation.json`, `ai-upgrade-dependency-audit.json` and `arm64-wheel-manifest.json`.

Provider and integration tests mock documented external HTTP responses, including 429, timeout, downtime, invalid JSON, wrong models, invented numeric claims and attempted tool calls. Real SQLite tests exercise concurrent budget reservations, crash/restart accounting, cache expiry/provenance, frequency/event gates, authentication, duplicate orders, risk rejection and preservation of reducing exits. Artificial market fixtures are explicitly labeled and never described as investment results.

## Behavior and limits

The quarter-hour quant engine and minute protection monitor remain separate from AI HTTP work. An AI worker checks eligibility after each quant cycle; normal LLM refresh is hourly, material events have a minimum interval, and every HTTP attempt reserves durable request/token capacity first. Unknown token usage retains the full conservative reservation. No automatic paid/provider/format fallback exists. Groq requires an explicitly selected account-visible model and declared account tier. Hermes requires explicit paid-access authorization; account billing is not verifiable from a key through the implemented catalog API.

Quant-only entries need a promoted accepted quantitative model and `PT_STRATEGY_EXECUTION_ENABLED=true`. AI-filtered/hybrid entries additionally need a compatible, accepted, explicitly approved strategy certificate. Failed, unavailable, stale or disagreeing AI means HOLD for dependent entries. AI cannot originate an entry from quant HOLD, bypass risk, or block quantitative/protective reductions. AI-only remains research-only. No strategy is currently active, and no AI-assisted execution certificate or invented performance report was created.

Structured validation restricts numeric claims, unsupported actions, timestamps, contradictions and executable output. It cannot prove the truth of every qualitative statement from an LLM. Displayed reasoning remains an untrusted opinion; news and macro context are explicitly unavailable. LLM confidence is never treated as a calibrated probability or combined through arbitrary weights.

Comparison uses only timestamped forward observations after the model's entire development dataset, with frozen model thresholds and chronological partitions. It never asks today's LLM to fabricate past forecasts. `forward_replay` uses estimated fills and remains separate from simulator and broker-paper results. Insufficient observations or failed gates correctly prevent approval. Use `compare-strategies SYMBOL --model VERSION` to isolate an existing model without deleting other versions.

Upstream pandas/NumPy/calendar and test-client deprecation warnings remain non-failing and should be reviewed when updating the lock.

## External verification still required

No Groq/Hermes keys, eligible paper broker credentials, GitHub deployment repository, Oracle host or public HTTPS backend hostname were supplied. Consequently no AI inference calls, paid calls, external broker orders, GitHub push, Community Cloud publication, Oracle provisioning, TLS issuance or cloud-systemd execution was performed. Local processes still depend on this machine; the prepared Oracle backend deployment is what removes that dependency.

Streamlit Community Cloud hosts **only the frontend**. Its app can sleep and its local storage is not durable; trading, model artifacts, budgets, SQLite, authentication and reconciliation stay on the Oracle VM. The cloud app stores only its public backend HTTPS URL and refresh interval, not broker keys, AI keys or the backend machine token.

## Commands and configuration

From the repository root:

```bash
source .venv/bin/activate
python -m pip install -r requirements.lock.txt
python -m pip install --no-deps -e .
papertrade init-db
python -m pytest -q --disable-warnings
```

Configure secrets privately on the backend. Groq setup needs `PT_GROQ_API_KEY`, `PT_AI_ACCOUNT_TIER=free` only after confirming the actual account plan, and an explicitly selected `PT_GROQ_MODEL`. `GROQ_API_KEY`/`GROQ_MODEL` aliases work too; use one spelling per value. Keep `PT_AI_ALLOW_PAID=false` and `PT_AI_FALLBACK_PROVIDER=none` for the default setup. Then:

```bash
papertrade ai-models --provider groq
# Set PT_GROQ_MODEL to an actual returned chat/JSON-capable model ID.
# Set PT_AI_ENABLED=true to authorize bounded analysis, not trading.
papertrade analyze-ai
papertrade ai-status
papertrade compare-strategies 'BTC/USD' --model QUANT_MODEL_VERSION
# Only after a candidate passes every gate:
papertrade approve-strategy VALIDATION_ID
```

These are strategy/configuration approvals, not per-order approval prompts. To run locally, use separate terminals for `papertrade serve`, `papertrade dashboard` and `papertrade scheduler`. Stop entries and request liquidation with `papertrade control kill`, keeping monitoring active until confirmed closed.

For laptop-independent operation, follow [DEPLOYMENT.md](../DEPLOYMENT.md) and enable the Oracle API plus engine/monitor/AI timers. Configure Caddy's HTTPS API hostname without exposing port 8000 publicly. In Community Cloud select **`cloud_dashboard/streamlit_app.py`**, Python **3.12**, and add only:

```toml
[papertrade]
api_url = "https://YOUR_ORACLE_API_HOSTNAME"
dashboard_refresh_seconds = 30
```

Full steps, bill-plan cautions and troubleshooting are in [AI_SETUP.md](AI_SETUP.md) and [STREAMLIT_CLOUD.md](STREAMLIT_CLOUD.md). Real provider catalog checks are separately opt-in with `PT_RUN_AI_INTEGRATION=true`; they never submit completions or orders.
