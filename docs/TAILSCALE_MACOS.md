# No-card macOS backend with Tailscale Funnel

This deployment keeps the authoritative SQLite database, models, API and scheduler on one Mac and publishes only the authenticated API through Tailscale Funnel. It needs no payment card, purchased domain, public IP address or router port forwarding. Streamlit Community Cloud remains the frontend.

The Mac is the server. Keep it connected to AC power, logged into the deployment user, awake and online. `caffeinate -s` prevents idle system sleep only on AC power; it does not make closed-lid operation reliable. macOS logout, reboot before login, power loss, Internet loss or a Tailscale outage interrupts operation. Freshness checks remain fail-closed after an interruption.

## Local public boundary

Install the direct-download Tailscale macOS application and sign into a free Personal tailnet. The application bundle exposes its CLI at:

```bash
TS_APP_BIN=/Applications/Tailscale.app/Contents/MacOS/Tailscale
"$TS_APP_BIN" status
```

Install Caddy with Homebrew. [`deploy/Caddyfile.tailscale`](../deploy/Caddyfile.tailscale) listens only on `127.0.0.1:8080`, accepts the public route allowlist, caps request bodies at 16 KB, adds security headers and proxies to FastAPI on `127.0.0.1:8000`. Funnel must point to Caddy rather than raw FastAPI:

```bash
brew install caddy
caddy validate --config deploy/Caddyfile.tailscale --adapter caddyfile
"$TS_APP_BIN" funnel --bg --yes http://127.0.0.1:8080
```

The first Funnel command opens an official Tailscale approval page. Approve Funnel for this device. Its stable public origin is then shown by:

```bash
"$TS_APP_BIN" funnel status
```

## Process supervision

This Mac uses these per-user LaunchAgents:

- `com.papertrade.api` runs the loopback FastAPI service.
- `com.papertrade.scheduler` runs analysis and independent protection monitoring.
- `com.papertrade.proxy` runs the loopback Caddy boundary.
- `com.papertrade.caffeinate` prevents idle system sleep while the Mac is on AC power.
- `com.papertrade.backup` creates a verified daily backup and bounds launchd logs.

The plists live in `~/Library/LaunchAgents/` and start after this user logs into the GUI. Inspect them with:

```bash
for service_label in com.papertrade.api com.papertrade.scheduler com.papertrade.proxy com.papertrade.caffeinate com.papertrade.backup; do
  launchctl print "gui/$(id -u)/$service_label" | head
done
```

Logs are private files under `var/` named `api-launchd.log`, `scheduler-launchd.log`, `caddy-launchd.log`, `caffeinate-launchd.log` and `backup-launchd.log`. The daily job retains seven verified generations under `var/daily-backups/`; see [the macOS backup runbook](MACOS_BACKUPS.md). A consistent pre-handoff backup is stored under `var/pre-tailscale-backups/`.

## Verification

Replace `YOUR_FUNNEL_HOST` with the hostname printed by Tailscale:

```bash
curl -fsS "https://YOUR_FUNNEL_HOST/healthz"
curl -fsS "https://YOUR_FUNNEL_HOST/readyz"
curl -sS -o /dev/null -w '%{http_code}\n' "https://YOUR_FUNNEL_HOST/status"
curl -sS -o /dev/null -w '%{http_code}\n' "https://YOUR_FUNNEL_HOST/openapi.json"
```

Expected responses are HTTP 200, 200, 401 and 404. Also verify a real dashboard login; do not weaken authentication to resolve a 401.

In Streamlit Community Cloud, open the app's overflow menu, then **Settings → Secrets**, and save only:

```toml
[papertrade]
api_url = "https://YOUR_FUNNEL_HOST"
dashboard_refresh_seconds = 30
```

Do not place the backend password, API token, broker credentials, AI keys or `.env` contents in Streamlit.

## Stop or remove public access

Disable Funnel without stopping local protection monitoring:

```bash
"$TS_APP_BIN" funnel --https=443 off
```

To stop a LaunchAgent, use `launchctl bootout gui/$(id -u)/LABEL`. Stopping the scheduler also stops minute protection, so first pause new entries and confirm any paper positions and orders are safely reconciled. The incident and shutdown procedure in [`DEPLOYMENT.md`](../DEPLOYMENT.md) still applies.
