# Backend handoff for an already-published dashboard

Publishing Streamlit does not create the Oracle backend, a durable database or provider credentials. The deployment helper makes the remaining server step reproducible once an existing Ubuntu VM and SSH access are available. It never provisions cloud resources or chooses a paid tier.

## Offline plan

Run from the existing repository:

```bash
.venv/bin/python scripts/deploy_backend.py ubuntu@YOUR_VM_HOST --api-hostname YOUR_API_HOSTNAME
```

This only prints the plan. It sends no SSH/HTTP request and changes no server, secret or trading state. An SSH alias from the local SSH configuration can replace `ubuntu@YOUR_VM_HOST`. For IPv6, configure an SSH alias. Optional `--identity /path/to/key` selects an existing identity without reading or copying its contents; optional `--port 22` selects the SSH port.

## Read-only host check

First verify the server's SSH host key through a trusted source and establish the trusted known-host entry. The helper requires strict host-key verification and noninteractive authentication; it does not disable either protection.

```bash
.venv/bin/python scripts/deploy_backend.py ubuntu@YOUR_VM_HOST --check
```

The check reports Ubuntu version, CPU architecture, Python version, rsync availability, noninteractive sudo availability and whether `/opt/papertrade` already contains an installation. It reads no broker/API keys, passwords, database rows or private key contents. If SSH is unavailable, the helper reports a sanitized failure rather than guessing connection success.

## Explicit fresh-host bootstrap

Only on a fresh Ubuntu 24.04+ host with Python 3.12+, supported ARM64/x86_64 CPU and authorized noninteractive sudo:

```bash
.venv/bin/python scripts/deploy_backend.py ubuntu@YOUR_VM_HOST --api-hostname YOUR_API_HOSTNAME --deploy
```

This command stages the existing source over SSH/rsync, invokes the existing installer and migrations, then enables the API and engine/protection/AI timers. It excludes local `.env` files, SQLite/model state under `var`, Git metadata, virtual environments, Streamlit secrets and private-key file extensions. It uses no rsync deletion flag. Source staging uses a unique directory and checks again for an existing installation before installing.

Bootstrap configuration is generated **on the server**. A random initial dashboard password is saved privately at `/opt/papertrade/var/initial-admin-password.txt` with mode `0600`; the backend configuration stores its hash and a generated machine token. Neither password nor token is printed or copied from the Mac. Save the password securely and remove that file after use. The existing installer remains interactive unless explicitly invoked with `PT_BOOTSTRAP_GENERATE=1`.

Paper mode, AI-off, paid-usage-off and strategy-execution-off defaults remain in effect. The helper does not add broker/AI keys, activate a model, approve a strategy or submit an order. Timers can collect data and report missing models/credentials while staying NO TRADE.

An existing nonempty or symlinked `/opt/papertrade` is refused. Use the backed-up update procedure in [DEPLOYMENT.md](../DEPLOYMENT.md) for an existing installation; the helper never overwrites it or deletes history.

Fresh bootstrap creates a separate empty server ledger. It **does not migrate the existing Mac's dataset, trading history or model artifacts**. Before enabling a strategy, restore a verified, consistent database/model backup on the server through the existing recovery procedure when continuing the same venue/account. Preserve account identity and unresolved order records, then reconcile paper broker state. Never copy live SQLite/WAL files independently or replace the new server's secrets with a local `.env` accidentally.

## Finish the public connection

The API hostname argument records the intended endpoint; it does not claim DNS ownership or configure HTTPS. Follow [DEPLOYMENT.md](../DEPLOYMENT.md) to verify DNS, install/validate the supplied Caddy API configuration and apply the correct host/Oracle firewall rules. Keep raw port 8000 private. The helper reports `https_verified: false` until those separate checks are actually completed.

Once the public HTTPS API is reachable and authenticated controls work, set only the backend URL in the published app's Community Cloud Secrets:

```toml
[papertrade]
api_url = "https://YOUR_API_HOSTNAME"
dashboard_refresh_seconds = 30
```

Keep Groq, Hermes, Alpaca and OANDA credentials on the VM. Use [AI_SETUP.md](AI_SETUP.md) to verify account plans and select available AI models. Provider credentials and accepted/promoted models still need real verification; a successful bootstrap does not establish a trading edge or authorize paid/live use.

The helper tests mock SSH and rsync. No actual remote deployment, TLS provisioning or provider connection was performed while adding it.

## Local follow-up verification — 2026-11-05

The complete suite passed with **261 tests passed and five external integration tests skipped**. Ruff passed for `src`, `tests`, `scripts` and `cloud_dashboard`; `pip check`, `alembic check` and the installer shell syntax check also passed. The local API and dashboard health endpoints returned HTTP 200, authenticated status returned 200, and unauthenticated status returned 401.

The running Mac exposed an operational limitation: `/readyz` returned 503 after sleep interrupted multiple quarter-hour analyses. macOS power logs confirmed sleep across those scheduled times, and APScheduler logged missed execution deadlines. The independent monitor resumed after wake. A manual analysis late in the interval rejected stale candles, as required by the existing freshness limit. Do not increase that limit or replay missed trading opportunities to hide a sleeping host; verify recovery on the next scheduled cycle and use the server deployment for laptop-independent operation.

Recovery was verified without a code or configuration change: the scheduled **14:00:20 UTC** analysis completed successfully, and `/readyz` returned **200** at 14:00:29 UTC with `online: true` and zero open positions. Before/after HTTP evidence is saved locally in Git-ignored `var/verification/backend-handoff-local-check.json`.

No Oracle SSH target or public API hostname was available in the project configuration or local SSH aliases. Provider credentials were also absent. Cloud deployment and provider verification remain outstanding. The local environment remains paper simulator mode with AI and strategy execution disabled.

## No-card backend selected — 2026-11-05

The operator declined Oracle because signup required a payment card and selected the no-card macOS/Tailscale layout documented in [TAILSCALE_MACOS.md](TAILSCALE_MACOS.md). Tailscale 1.104.5 is connected on the direct-download macOS variant. Funnel publishes a stable `*.ts.net` HTTPS origin through loopback Caddy; raw FastAPI remains bound to `127.0.0.1:8000`.

The API, scheduler, Caddy proxy, AC-power sleep assertion and verified daily backup are supervised by per-user LaunchAgents. The daily backup keeps seven verified generations and bounded launchd logs; before the handoff, a separate verified SQLite backup was created under `var/pre-tailscale-backups/`. Local and public checks observed health/readiness 200, unauthenticated status 401, blocked OpenAPI 404, wrong-method 404 and oversized-body 413. Authenticated login/status succeeded, with zero positions and strategy execution still disabled.

This removes the cloud payment-card requirement but does not make the laptop independent. Operation stops during logout, reboot before login, closed-lid sleep, power/Internet loss or a Tailscale outage. Keep the Mac connected to AC, logged in, awake with its lid open and online.
