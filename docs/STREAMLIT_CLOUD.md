# Streamlit Community Cloud dashboard

The existing dashboard can run on Streamlit Community Cloud while the engine, FastAPI backend, broker integrations, AI provider credentials, model artifacts and SQLite database stay on one persistent backend host. The backend can be an Oracle VM or an always-on computer published through Tailscale Funnel. The latter avoids a payment card but depends on that computer, its power and its Internet connection.

Community Cloud is a dashboard host here. Its apps [sleep after twelve hours without traffic](https://docs.streamlit.io/deploy/streamlit-community-cloud/manage-your-app), and its local filesystem [does not guarantee durable storage](https://docs.streamlit.io/develop/concepts/connections/connecting-to-data). The engineering consequence is that a continuously operating trading scheduler and its authoritative ledger belong on the VM. Waking, rebooting or redeploying the dashboard must not create orders or reset trading state.

## Prepare the backend

For Oracle, install/update the application with [DEPLOYMENT.md](../DEPLOYMENT.md). For the current no-card macOS layout, use [TAILSCALE_MACOS.md](TAILSCALE_MACOS.md). Apply migrations and keep the API, scheduler and independent protection monitor supervised. Neither layout requires a GPU or local large language model. Keep broker and AI keys only in the backend's protected `.env` file.

Expose FastAPI through the supplied constrained reverse proxy and a valid public HTTPS origin. Oracle can use Caddy and a controlled DNS hostname; the no-card layout uses a stable Tailscale Funnel `*.ts.net` hostname. FastAPI stays bound to loopback behind the proxy, and raw port 8000 remains private. Preserve authentication on `/auth/login`, `/status`, `/tables/*` and `/controls`. Liveness `/healthz` is not proof that the scheduler is ready; `/readyz` must reflect current engine observations.

The Community Cloud server makes HTTPS requests to this API; browser CORS access is unnecessary. Do not add a wildcard CORS bypass or put an administrator machine token in the public app. Community Cloud outbound IPs may change, so any network allowlist must follow the [current Streamlit environment documentation](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/file-organization).

Confirm the backend can remain running for the intended operating period. In the Tailscale Mac layout, keep the Mac logged in, connected to AC, awake with its lid open, and online. Preserve the dedicated minute monitor, reconciliation, backups and external downtime heartbeat. Without a running backend and public HTTPS endpoint, the cloud dashboard will show unavailable status and cannot replace the backend.

## Deploy the frontend

1. Put the existing repository in a GitHub repository you administer. Review the changes and secret exclusions before pushing. No GitHub repository or Community Cloud app is created automatically by this implementation.
2. In [Streamlit Community Cloud](https://share.streamlit.io), create an app from that repository and branch.
3. Set the entrypoint to **`cloud_dashboard/streamlit_app.py`**, not the trading CLI or local dashboard path.
4. In Advanced settings, select **Python 3.12**.
5. In the app's Secrets settings, paste the following and replace the URL with the actual VM API hostname:

```toml
[papertrade]
api_url = "https://api.your-domain.example"
dashboard_refresh_seconds = 30
```

Only those settings belong in Community Cloud. Do not add Alpaca, OANDA, Groq or Hermes keys, the backend password hash, `PT_API_TOKEN`, broker account IDs, database paths or `.env` contents. Sign in through the existing dashboard form using the backend administrator username/password; the backend returns a short-lived session token stored in that Streamlit session. Changing the configured backend invalidates that session before its token can be sent to another origin.

The URL must be a public HTTPS origin, without embedded credentials, query strings, fragments or path prefixes. HTTP external hosts, localhost, private IPs and metadata-service IPs are refused. There is no automatic fallback to a local backend or sample data. Redirects are not followed and TLS verification stays enabled.

The [dependency selection rules](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/app-dependencies) give the entrypoint directory's `requirements.txt` precedence over the root dependency file. `cloud_dashboard/requirements.txt` therefore installs frontend libraries only; LightGBM, the scheduler, SQLAlchemy and broker execution code are not loaded by this app. No `packages.txt`, GPU, OpenMP runtime or model download is needed for the frontend. The subdirectory's `.streamlit/config.toml` overrides the local loopback bind for cloud hosting, following the [documented file-organization rules](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/file-organization).

Use the Community Cloud app's access/sharing settings to limit its audience where available; backend authentication remains mandatory for private data and every control. See the official [secrets-management guide](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/secrets-management).

## Optional local frontend check

The existing local dashboard command remains unchanged:

```bash
.venv/bin/papertrade dashboard
```

To test the Community Cloud entrypoint locally, create a Git-ignored `.streamlit/secrets.toml` with the same `[papertrade]` HTTPS configuration, then run:

```bash
.venv/bin/python -m streamlit run cloud_dashboard/streamlit_app.py
```

This still needs a reachable public HTTPS backend. It does not start an engine, initialize a database or submit orders.

## New views and result integrity

**AI analysis** reads stored provider status, validated responses, quantitative predictions, fusion decisions and request/token/latency/error records from authenticated API routes. Missing records remain unavailable. Provider narratives are rendered as plain text; they cannot execute code, invoke tools or authorize trades. LLM confidence is explicitly an uncalibrated opinion.

**Strategy comparison** shows each stored result source separately. Backtests, research observations, local simulated fills and broker-hosted paper results are not merged into one return series. A recommendation or decision observation is not an executed order. Empty history does not become a zero-return or profitability claim.

**System health** reads the backend's host/resource/database, scheduler, broker, provider, data and reconciliation observations. A reachable Streamlit page never changes the backend's ONLINE status.

## Troubleshooting and verification boundary

- A configuration error means Secrets lacks a valid public HTTPS URL, or contains unsupported settings. The error deliberately does not echo secret values.
- “Backend unavailable” means DNS, TLS, firewall, proxy or VM/API access failed; it does not mean the engine is stopped or positions are closed. Check the VM and external heartbeat separately.
- HTTP 401 signs the session out. Sign in again after token expiry or a backend change. Do not bypass authentication to fix it.
- HTTP 429 on login means rate limiting is active; wait and inspect the VM/proxy logs. Do not disable throttling for a public endpoint.
- A sleeping dashboard can be woken through Community Cloud. It should not affect the running VM engine or authoritative database.
- Local tests use Streamlit AppTest and mocked HTTP to verify authentication, HTTPS rejection, source separation, missing-data behavior and new views. They do not prove Community Cloud publication, Oracle networking, certificates or real provider connectivity. Those require the user's accounts and deployed endpoint.

The frontend needs no paid subscription by design. Oracle availability, networking, domain/certificate arrangements and AI account plan limits still require independent verification. No paid fallback is selected automatically.
