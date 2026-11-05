# Existing platform audit and minimal-change plan

The upgrade extends the existing `src/papertrade` application. No competing application, database reset, record deletion or replacement of paper brokers is required.

## Reuse

The repository already has genuine Coinbase/Alpaca/OANDA market-data adapters, completed-candle validation and calendars, causal features, per-symbol calibrated LightGBM artifacts with explicit acceptance, chronological backtests, shared independent risk approval, persistent paper execution/reconciliation, SQLite/Alembic, quarter-hour scheduling and minute protection checks, authenticated FastAPI controls, a Streamlit client, backups and Oracle/systemd deployment files. Existing records and all original tests are retained.

## Gaps and changes

1. Add Groq and optional Nous Hermes adapters behind one validated, evidence-only analysis contract. Provider keys and model IDs are missing; no real provider connection can be claimed.
2. Add durable per-attempt request/token reservations, validated response storage, frequency/event gates and cache provenance. Account free/paid status cannot be inferred reliably from an API key; require explicit account-tier configuration and never automatically use paid fallback.
3. Preserve the quantitative `decide()`/risk/ML interfaces and add a separate fusion gate. AI can veto entries; it cannot originate unsupported entries, authorize broker calls or block independent protective exits. Assisted execution needs an explicitly approved validation certificate. Initial execution authorization is off.
4. Run AI HTTP work outside the trading execution lock. Slow providers must not block minute protective monitoring. Quantitative analysis continues at fifteen minutes even when AI is unavailable.
5. Add tables for AI analyses, individual request attempts, strategy observations and strategy validations through an additive migration. Existing trading tables/history remain intact.
6. Extend the current dashboard with actual stored AI/strategy/health data. A thin Community Cloud entry point calls the Oracle backend over HTTPS; it has no broker/AI credentials and starts no trading engine or database.
7. Add a separately scoped HTTPS API proxy for the Community Cloud client, resource/reconciliation health, deployment instructions and mocked/provider/strategy regression tests.

## Reliability/security findings

Community Cloud local storage is not durable and dashboard availability does not establish engine health. Keep authoritative SQLite and scheduling on Oracle. Existing remote API deployment was loopback-only; exposing it now requires HTTPS, authentication, rate limits and sanitized logging. All external AI text is untrusted. Response schema validation cannot establish the truth of unrestricted prose, so the first implementation deliberately restricts evidence vocabulary and numeric claims. Historical LLM calls made today are not historical evidence: strategy comparison must use responses recorded before the relevant outcome, and label replay separately from executed paper performance.

## Implementation order

Preserve/backup state and run the baseline tests; add configuration/schema/migration; implement providers, durable analysis service and strategy validation; integrate cache-only fusion into the existing engine; add dashboard/HTTPS/Community Cloud deployment; run original and new tests, migration checks and local HTTP startup verification. No cloud resources, paid AI calls, GitHub publication or live trading are enabled by implementation.
