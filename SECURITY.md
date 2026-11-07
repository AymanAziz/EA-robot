# Security model

## Paper-only authority

`PT_MODE` only accepts `paper`. Alpaca requests go to the hardcoded paper host; OANDA requests go to the hardcoded Practice host. Execution adapters reject unsupported hosts/redirects and never use a user-supplied live URL. Live credentials cannot switch environments. No live adapter or withdrawal functionality exists. Credentials belonging to another environment should fail authentication rather than redirect trading authority.

The local simulator is persistent but is not a broker account. Its fills are clearly labeled. External provider failures are not converted into simulated success. This code has not been authorized to handle real funds.

## Secrets

Use `.env` or server environment variables; `.env` is ignored by Git and excluded from Docker builds. `.env.example` contains no real secrets. `scripts/configure_env.py` stores an Argon2 password hash and random backend token without exposing the password to command-line history. Keep the real file at mode `0600` and grant only the application account and operators access. Never put API keys, tokens or password values in screenshots, issue bodies, dashboard tables, model metadata or logs.

Groq/Hermes keys belong only on the persistent backend host. Streamlit Community Cloud receives only its public HTTPS backend URL and display refresh setting; users authenticate through the existing login form. Do not copy the backend host's `.env`, administrator password hash, machine bearer, brokerage account IDs or AI keys into Community Cloud Secrets. Actual `.streamlit/secrets.toml` files are Git-ignored; the checked-in example contains no credentials. AI requests contain bounded market evidence and open-position facts, which is an intentional transfer to the selected third-party provider; do not append personal/account/credential material to that context.

Use dedicated paper/practice credentials with the minimum account authority the provider offers. Rotate credentials if exposed, and rotate the backend token after suspected session compromise. Do not print resolved Compose configuration or enable wire-level HTTP debug logs. The dashboard only receives authenticated system records; configuration objects and raw provider headers are not a dashboard response.

Backups and model artifacts can contain account identifiers and trade history. Encrypt off-host backups. The backup script deliberately excludes `.env`; preserve secrets through a separate protected mechanism.

## Authentication and authorization

The backend checks password authentication against an Argon2 hash. A high-entropy bearer authenticates subsequent backend operations; the dashboard stores it in server-side Streamlit session state after login. Every control request is authorized again on the backend and audited. Hiding a button is never an authorization mechanism. Invalid or missing credentials must fail closed, including when an operator forgot to configure authentication.

The API and local Streamlit bind to loopback by default. Public access requires HTTPS through the supplied Caddy templates, or an SSH tunnel that keeps both ports private. A self-hosted dashboard can leave the API entirely private. Community Cloud instead needs the separate `deploy/Caddyfile.api` HTTPS API proxy; it exposes only the required route/method allowlist and preserves backend authentication. Never expose raw port 8000/8501 or administrative routes over public HTTP. No wildcard CORS bypass is required: Community Cloud sends server-side requests. Keep Streamlit XSRF/CORS protections enabled. A secure reverse proxy, firewall, OS updates and an administrator-only account are part of deployment, not implied by a passing unit test.

Community Cloud rejects HTTP external backends, private/loopback/metadata IPs, credential-bearing URLs and redirects. Its short-lived session bearer is bound to the configured origin; changing origins clears it before another request. Configurations must come from the trusted deployment administrator, never from model output or a public URL input. Validate proxy-header trust and login throttling on the actual public Caddy deployment; never trust an arbitrary caller's forwarded IP header.

This is a single-administrator application, not a multi-tenant identity system. A stolen authenticated session grants paper trading controls. Keep sessions short, sign out from shared machines, and rotate/restart after suspected compromise. An Internet-facing deployment should add a trusted access gateway or IP restrictions where appropriate. Multiple API workers are unnecessary for this deployment and can complicate process-local rate limits; run one worker.

## Execution integrity

The risk engine independently enforces capped exposure, quantity/risk budgets, daily loss, drawdown, stale data, excessive spread, sessions and kill state. Limits apply across the combined portfolio rather than allowing each broker the full budget. Models cannot bypass it. Long entries have no leverage, no averaging down and no martingale. SELL/CLOSE are reductions only.

Order intents and unique client IDs are persistent before submission. Unknown responses remain uncertain until lookup/reconciliation resolves them; the platform does not blindly retry a POST or assume a canceled/filled status. A database restore must be reconciled with the actual broker before entries resume. Use dedicated paper accounts to avoid external orders changing the portfolio unexpectedly.

Hosted stop/target orders are preferred but do not guarantee an exact fill price. Alpaca crypto lacks hosted bracket protection and remains entry-disabled by default. Software monitoring is an explicit paper-only opt-in requiring healthy independent minute monitoring and a recent successful external-watchdog heartbeat. The durable, policy-bound holding expiry is independent of model availability. Host downtime, provider outages and price gaps remain risks even with those controls.

## Untrusted AI and spending authority

The provider has no code, SQL, filesystem, broker, withdrawal or unrestricted network tools. A strict Pydantic action allowlist/evidence schema rejects unknown symbols, unsupported or contradictory actions, stale/future timestamps, invalid/missing JSON fields, invalid confidence, numerical narrative claims and tool/code/markup content. External response text is displayed as plain text. No external news/text is accepted by default; adding a verified source later must preserve its data-only treatment and cannot grant prompt instructions authority.

An AI recommendation can veto a quant entry under the selected validated policy; it cannot create a quant trade or change sizing/risk, authenticated controls, session availability or paper-only configuration. `ai_only_research` never executes. AI-assisted execution requires a current accepted and explicitly approved strategy certificate; provider/model/source-policy changes or expiry invalidate it. Source/report checksums support local integrity, not external authenticity or authorization; protect the database and administrator account. A model-provided certificate or approval field has no authority.

AI is disabled by default, with `PT_AI_ACCOUNT_TIER=unverified`, `PT_AI_ALLOW_PAID=false` and fallback `none`. Account-plan declarations cannot establish actual billing entitlement. Operators must verify provider-side plan/model access and limits before declaring a free Groq account. Hermes requires explicit paid-access authorization and never becomes an automatic fallback. Durable daily request/token reservations include retries and remain charged when usage is unknown. Local ceilings are defense in depth, not provider billing guarantees or organization-wide spending controls.

## Storage and process isolation

SQLite and simulator ledgers are local to one machine. WAL enables concurrent reads with short transactions; it is not a clustered database. Do not mount state on NFS or allow several hosts to run the same engine. Preserve unique constraints, migrations and order journals; deleting state to clear an error can create duplicate orders.

Deployment services run as the unprivileged deployment user with a restricted write directory, private temporary files and appropriate process supervision for the host. The AI worker has a separate process/lock so slow provider HTTP does not hold the trading execution lock. Do not run the engine as root. Restrict inbound networking at both the public proxy/tunnel and host-firewall layers. Back up with the SQLite backup API; restore databases only with all writers stopped, including the AI worker, no stale WAL files and an explicit paused reconciliation. Preserve AI usage reservations and strategy approval provenance during recovery rather than resetting a daily budget by deleting records.

## Dependency and source review

```bash
python -m pip_audit
python -m pytest -q
python -m ruff check src tests
```

Review every dependency finding against the installed version and deployment exposure; resolve or explicitly record material findings before public use. Follow official security advisories and update within the declared compatibility ranges only after tests pass. A clean dependency scan is not a penetration test. Production deployment configuration, TLS renewal, firewall exposure, backup restoration and external heartbeat delivery need tests on the target backend host.

## Incident response

1. Record emergency stop and pause new entries if the backend is reachable.
2. Inspect the provider's paper console and actual open orders/positions; close/cancel deliberately and reconcile confirmations.
3. Stop scheduling if the host cannot be trusted; never resend an uncertain intent with a fresh client ID.
4. Rotate exposed credentials and backend tokens, preserve sanitized audit records and restore a reviewed environment.
5. Verify a paused full reconciliation before resuming any paper entries.

Report vulnerabilities privately to the repository owner with sanitized reproduction steps. Do not include credentials or personal account information in public reports.
