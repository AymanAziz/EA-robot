# Deployment and recovery

## Cost and host selection

Use an Ubuntu 24.04 ARM64 image on an Oracle A1 Flex instance marked **Always Free eligible** in your tenancy's home region. Start with 1 OCPU and 6GB RAM; CPU-only LightGBM with one worker, SQLite, FastAPI and Streamlit fit this target. Keep historical data retention bounded and train one symbol at a time. No GPU, managed database, paid market feed or LLM service is used.

At the documentation check on 2026-11-05, Oracle's published A1 allowance was 1,500 OCPU-hours and 9,000 GB-hours per month, equivalent to approximately 2 OCPUs and 12GB continuously. Check the [current allowance](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm) in your own tenancy before provisioning. Home-region capacity is not guaranteed and Oracle may reclaim idle instances. RM0 is conditional on free eligibility and staying within all quotas; disk, network, backups, domain registration and upgrades can add cost. Configure budgets/alerts and compartment quotas. Do not upgrade or provision paid resources as a workaround without reviewing their price.

The server runs independently of the laptop. If Oracle capacity is unavailable, the supplied local deployment remains usable while that machine stays on; a cloud VM has not been provisioned by this repository.

The requested hosted frontend is **Streamlit Community Cloud**, connected over authenticated HTTPS to this VM's FastAPI backend. The VM retains all execution, SQLite/model history, provider credentials and background timers. Community Cloud can sleep or discard local files without interrupting VM execution; use [docs/STREAMLIT_CLOUD.md](docs/STREAMLIT_CLOUD.md) for its exact entrypoint/secrets settings.

## Install on Ubuntu

Copy/clone the repository to the server over SSH, verify the source and run:

```bash
bash scripts/install_ubuntu.sh
```

The script installs Python/OpenMP packages, a dedicated unprivileged `papertrade` account, a virtual environment in `/opt/papertrade/.venv`, the exact Python dependency versions from `requirements.lock.txt`, the application, secret setup, the database and systemd unit files. It does not start automatic execution. It requires `sudo` for OS packages and service installation; trading processes run without root. Application state is under `/opt/papertrade/var` and configuration under `/opt/papertrade/.env` with mode `0600`.

For an **existing installation**, preserve `.env` and databases, pause entries, stop analysis/monitor/AI/API writers, and take a verified backup before installation/migration. The installer preserves `.env` and state; do not replace them with templates. New settings have safe disabled defaults and can be added selectively. Set `PT_DEPLOYMENT_ENVIRONMENT=oracle` on the VM so actual host telemetry is labeled correctly. Keep the locked Python 3.12 environment; the Community Cloud frontend has its own lightweight dependency file and also selects Python 3.12.

Privately edit `.env` with the required **paper/practice** credentials. Keep `PT_MODE=paper`. Set `PT_EXECUTION=brokers` only for broker-hosted paper orders; the default `simulator` is a separate local venue. Use `sudo -u papertrade` to run commands as the application user:

Each venue/account needs isolated state: before the first broker run set `PT_STATE_DIR=var/brokers` and `PT_DATABASE_URL=sqlite:///var/brokers/papertrade.db`. Run initialization, collect data and train for that provider. Never reuse simulator equity/fills or Coinbase model history as an Alpaca account history. Execution venue changes, hashed account identity changes and mixed candle sources are rejected. Preserve old state for audit; do not delete unresolved order records to force a retry.

```bash
cd /opt/papertrade
sudo -u papertrade .venv/bin/papertrade init-db
sudo -u papertrade .venv/bin/papertrade verify-brokers
PT_HISTORY_START="$(python3 -c 'from datetime import datetime,timedelta,timezone; print((datetime.now(timezone.utc)-timedelta(days=90)).isoformat())')"
PT_HISTORY_END="$(python3 -c 'from datetime import datetime,timezone; print(datetime.now(timezone.utc).isoformat())')"
sudo -u papertrade .venv/bin/papertrade collect 'BTC/USD' --start "$PT_HISTORY_START" --end "$PT_HISTORY_END"
sudo -u papertrade .venv/bin/papertrade train 'BTC/USD'
sudo -u papertrade .venv/bin/papertrade backtest 'BTC/USD' --model VERSION_FROM_TRAINING
sudo -u papertrade .venv/bin/papertrade promote 'BTC/USD' VERSION_FROM_TRAINING
```

Use the version printed by training. A rejected candidate cannot be promoted; keep NO TRADE if no strategy passes. Repeat per supported symbol using the appropriate data credentials. Promotion is never a workaround for poor validation.

## Dashboard access

For **Community Cloud**, only the API service needs to run on this VM. Configure the public API proxy:

```bash
sudo systemctl enable --now papertrade-api.service
sudo apt-get install -y caddy
sudo cp deploy/Caddyfile.api /etc/caddy/Caddyfile
sudoedit /etc/caddy/Caddyfile
sudo caddy validate --config /etc/caddy/Caddyfile
sudo systemctl enable --now caddy
sudo systemctl reload caddy
```

Replace `api.example.com` with a real DNS hostname, configure its A/AAAA record and verify a trusted HTTPS certificate. This template proxies only the needed GET/POST routes to loopback FastAPI. Every private-data/control route remains bearer-authorized by the backend; login remains password-authenticated/rate-limited. Check anonymous controls return 401 and that proxy-header/client-IP handling works before deploying the frontend. Never publish raw port 8000. A domain or alternative trusted certificate arrangement may have a cost. Paste only `[papertrade] api_url="https://YOUR_API_HOST"` and its refresh setting into Community Cloud Secrets; deploy entrypoint `cloud_dashboard/streamlit_app.py` with Python 3.12 following [the cloud guide](docs/STREAMLIT_CLOUD.md).

The existing VM-hosted dashboard and SSH-tunnel options remain available below. They are optional when Community Cloud is used.

Start the local backend and dashboard:

```bash
sudo systemctl enable --now papertrade-api.service papertrade-dashboard.service
```

For zero domain cost, keep ports 8000 and 8501 private and use an encrypted SSH tunnel from the laptop:

```bash
ssh -L 8501:127.0.0.1:8501 ubuntu@SERVER_IP
```

Open <http://127.0.0.1:8501> locally and log in. The browser-to-server connection travels inside SSH; do not expose a plaintext public dashboard. Closing the tunnel does not stop the engine.

For browser access without SSH, use an existing DNS name with HTTPS:

```bash
sudo apt-get install -y caddy
sudo cp deploy/Caddyfile /etc/caddy/Caddyfile
sudoedit /etc/caddy/Caddyfile
sudo caddy validate --config /etc/caddy/Caddyfile
sudo systemctl enable --now caddy
sudo systemctl reload caddy
```

Replace the example hostname before validating. Point its A/AAAA records at the server. Caddy terminates HTTPS and proxies only Streamlit on loopback; FastAPI has no public proxy route. Keep CORS and XSRF protection enabled. Caddy's [automatic HTTPS requirements](https://caddyserver.com/docs/automatic-https) include DNS resolution and reachable ports 80/443. A domain can have its own cost. Check certificate renewal and browser trust before using controls.

Apply matching Oracle NSG/security-list and host-firewall rules:

- SSH port 22 only from your administrator IP/CIDR where practical.
- TCP 80/443 only when using the public HTTPS proxy.
- No inbound 8000/8501 and no externally accessible SQLite or Docker management port.
- Outbound HTTPS for providers, certificate renewal, dependency downloads and the optional watchdog; DNS/NTP as required.

An Ubuntu UFW example is below. Replace the CIDR before use, keep your current SSH session open and verify a second connection before logging out. Oracle's networking rules are separate from UFW and may include existing host iptables rules.

```bash
sudo ufw allow from ADMIN_IP_CIDR to any port 22 proto tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
sudo ufw status verbose
```

For tunnel-only access, omit the 80/443 rules.

## Automatic operation

Inspect and start the timers:

```bash
sudo systemd-analyze calendar '*-*-* *:00,15,30,45:20 UTC'
sudo systemctl enable --now papertrade-engine.timer papertrade-monitor.timer papertrade-ai.timer
sudo systemctl list-timers 'papertrade-*'
sudo -u papertrade .venv/bin/papertrade run-once
sudo -u papertrade .venv/bin/papertrade status
```

The analysis timer runs twenty seconds after each completed quarter-hour. `Persistent=true` allows one missed-run catch-up after reboot; the application evaluates the latest completed candle, not a backlog of outdated trading opportunities. A shared lock and durable identifiers prevent overlap/repeated submissions. The minute monitor runs at second 10, reconciles balances/orders, checks software protection and observes circuit/kill state independently of model analysis. The AI timer checks frequency/event gates at second 40 after each quarter-hour and normally calls the provider hourly, not every wake. It has a separate `ai.lock` and does not hold `engine.lock` while waiting for an LLM. Disabled AI produces no provider request. Provider/credential failures remain visible and block only dependent new entries; risk-reducing protection continues.

Do not run `papertrade scheduler` at the same time as systemd timers. If using APScheduler instead, keep that single process supervised and stop/disable all three timers first. In either deployment, order lookup and broker reconciliation occur before restart entry decisions. Unknown submissions remain blocked until resolved; removing the database or changing client IDs to force a retry is unsafe.

API and dashboard services restart on failure. The engine is a oneshot job invoked again by the timer; it does not automatically retry uncertain mutations. Clock synchronization matters: verify `timedatectl status` and use UTC logs. Resource limits in the units are conservative and can be tuned after measurement; a killed process still requires reconciliation before resumed entries.

## Configure and enable AI deliberately

Use [docs/AI_SETUP.md](docs/AI_SETUP.md) to verify a Groq account plan, discover the actual available model catalog, configure structured output, set durable budgets and enable analysis. Hermes requires explicit paid authorization; fallback remains `none`. Provider keys stay only in the protected VM `.env`. No GPU or local LLM is installed.

```bash
sudo -u papertrade .venv/bin/papertrade ai-models --provider groq
sudo -u papertrade .venv/bin/papertrade ai-status
sudo -u papertrade .venv/bin/papertrade analyze-ai
sudo -u papertrade .venv/bin/papertrade compare-strategies 'BTC/USD'
sudo journalctl -u papertrade-ai.service --since today -o cat
```

AI analysis and new strategy execution remain off by default. Existing LightGBM promotion remains an independent prerequisite. Quant-only needs explicit strategy enablement; AI-assisted modes also require a passing current comparison and `papertrade approve-strategy VALIDATION_ID_FROM_COMPARISON`. AI-only stays research-only. No human approval is needed for individual supported paper orders after validated strategy activation. Never enable a strategy simply to make a deployment dashboard look active; failed/insufficient evidence must remain NO TRADE.

## Protection and downtime

Broker-hosted stop/target orders are preferred and are attached where supported. Alpaca crypto has no supported bracket protection and new remote crypto entries are disabled by default. Setting both `PT_ALLOW_UNHOSTED_PROTECTION=true` and a monitored `PT_WATCHDOG_URL` is an explicit opt-in for paper software protection; the engine also requires healthy independent minute monitoring and a recent successful watchdog heartbeat before those entries can pass. A configured URL alone is insufficient and successful delivery alone does not prove an alert recipient is watching. The durable, policy-bound holding expiry requests exits even if a model becomes unavailable. Stops and time exits still have slippage/gap risk and cannot guarantee execution during an outage. Do not use this opt-in to infer suitability for real money.

Configure an external heartbeat receiver with a short deadline/grace period for the independent monitor. Put its HTTPS ping URL in `PT_WATCHDOG_URL`. Arrange email or another external notification from that receiver when pings stop. Test by stopping the monitor temporarily and confirm an alert arrives, then restore it. A receiver can run on another machine you control; optional third-party free plans have their own quotas and terms. Never include broker keys in the heartbeat URL or payload.

The dashboard's ONLINE flag requires actual recent engine/data/broker/protection-monitor success. `/healthz` only establishes process liveness. `/readyz` returns HTTP 200 only while recent observations establish ONLINE; otherwise it returns HTTP 503. Use readiness/status for trading readiness. An external monitor must not mark the engine healthy simply because Streamlit responds. For a private API deployment, use outbound heartbeat monitoring or a private-network authenticated probe. The Community Cloud API proxy may expose the terse liveness/readiness routes over HTTPS; detailed status remains authenticated.

Optional email alerts can be configured in the external heartbeat receiver; no Telegram account or paid notification service is required. This keeps SMTP secrets and delivery dependencies outside the execution path.

## Logs, health and routine checks

```bash
sudo journalctl -u papertrade-engine.service -u papertrade-monitor.service -u papertrade-ai.service --since today -o cat
sudo journalctl -u papertrade-api.service -u papertrade-dashboard.service -f
sudo systemctl status papertrade-api.service papertrade-dashboard.service
sudo systemctl list-timers 'papertrade-*'
sudo -u papertrade .venv/bin/papertrade status
df -h /opt/papertrade
sudo -u papertrade .venv/bin/papertrade ai-status
```

The database stores risk events, health records, execution runs, signals, orders and fills. Application output is structured JSON and systemd sends it to journald. Bound journal disk use in `/etc/systemd/journald.conf` (for example `SystemMaxUse=200M`, `MaxRetentionSec=14day`) and restart journald after reviewing the host's other workloads. `deploy/papertrade-logrotate` covers optional `var/*.log` sinks; it does not rotate the SQLite database or bypass journald retention. Never enable HTTP debug logs containing authorization headers.

Review model age/validation, data freshness, unresolved orders, equity/daily loss and broker connectivity. Free APIs can rate-limit, change entitlements or suffer outages. Credentials do not imply all markets are supported. Errors and NO TRADE states are operational results to inspect, not reasons to bypass a risk gate.

## Safe stop and incidents

For a planned stop with the backend available:

```bash
cd /opt/papertrade
sudo -u papertrade .venv/bin/papertrade control pause
sudo -u papertrade .venv/bin/papertrade control close_all
sudo -u papertrade .venv/bin/papertrade monitor-once
sudo -u papertrade .venv/bin/papertrade status
```

Confirm broker positions are flat and pending/uncertain orders are resolved before stopping the monitor. The close command is a request; rejected/closed-market requests do not mean the portfolio is flat. Keep monitoring if positions remain and use the provider's paper console to investigate.

```bash
sudo systemctl stop papertrade-engine.timer
sudo systemctl stop papertrade-engine.service
sudo systemctl stop papertrade-ai.timer papertrade-ai.service
# Stop monitoring only after reconciling or consciously accepting outstanding paper exposure.
sudo systemctl stop papertrade-monitor.timer papertrade-monitor.service
```

For an emergency, record `papertrade control kill` first. A persisted kill prevents new entry decisions across restarts; an order already in flight can still be accepted by the broker after the stop request, so follow the close-and-reconcile procedure when connectivity allows. If the API/host is unavailable, disable the timers/process externally and inspect the broker's **paper** console for orders and positions. Do not submit another same-direction order to guess whether an uncertain submission filled. Pause/kill controls and provider confirmations must be checked after recovery. An explicit `resume` clears the kill latch; daily-loss and drawdown circuits remain independent.

## Backup and restore

SQLite WAL files cannot be treated like static CSV files. `scripts/backup.py` uses SQLite's online backup API and integrity checks. For one coherent snapshot of both the platform and local simulator ledger, pause entries and stop **all** writers (analysis, monitor and API controls), then back up:

```bash
cd /opt/papertrade
sudo -u papertrade .venv/bin/papertrade control pause
sudo systemctl stop papertrade-engine.timer papertrade-monitor.timer papertrade-ai.timer
sudo systemctl stop papertrade-engine.service papertrade-monitor.service papertrade-ai.service
sudo systemctl stop papertrade-dashboard.service papertrade-api.service
sudo -u papertrade .venv/bin/python scripts/backup.py --state-dir var --destination var/backups
```

Copy the timestamped backup to encrypted storage on another machine; retain several generations and test restoration. Preserve `.env` separately with encryption and access controls; the backup tool intentionally does not copy secrets. Include model artifacts, accepted version metadata and the exact source/dependency lock used. Back up before migrations or updates. Monitor remaining disk and apply a retention policy to backup directories.

AI usage reservations, cached evidence, forward observations and strategy certificates are in the same application database and must be preserved. A restored usage snapshot cannot account for provider requests made afterward; inspect the provider account and remain conservative before re-enabling AI. If an administrator used a custom database/model path outside `var`, include it explicitly rather than assuming the default backup directory covers it.

To restore, keep all writers stopped. Move the existing `var` directory aside, create a new `var`, copy the backup databases and `models` into it, set ownership to `papertrade`, and retain `0600` database permissions. Do not combine restored `.db` files with old `-wal`/`-shm` files. Restore the matching code/version, run `papertrade init-db` to apply migrations, start only the backend and explicitly record pause before any engine run. Reconcile the actual remote paper account first: its history continued independently of the restored database. Inspect unknown orders and client IDs; restoring a snapshot never authorizes duplicate submissions.

Restart the API/dashboard, run one paused analysis/monitor cycle, verify positions/fills and health, then enable timers and deliberately resume paper entries when appropriate. Restoration and cloud provisioning require an operator test in the target environment; local unit tests cannot certify them.

## Optional Docker Compose

Native systemd is the primary low-overhead deployment. Compose is supplied for ARM64/x86_64 hosts with compatible LightGBM wheels/runtime and Docker installed:

```bash
docker compose build
docker compose run --rm api papertrade init-db
docker compose up -d
docker compose logs -f engine
```

The named `state` volume holds databases and artifacts; API and engine share it on one host. Run collection/training/promotion/AI commands with `docker compose run --rm api papertrade ...`. The dashboard is published only on host loopback and the API has no published port in the supplied Compose file. This preserves the original private deployment; the native API+Caddy configuration above is the documented Community Cloud backend. If adapting Compose, a reviewed TLS reverse proxy must reach its private API network; do not publish raw 8000 to make Community Cloud work. Docker uses its own firewall rules; verify effective exposure independently of UFW. Do not run native systemd timers alongside the Compose scheduler. A container restart does not erase the durable order journal or AI usage reservations.

`.env` must exist on the host with configured password hash and random token before Compose starts. Dollar signs in an Argon2 hash can interact with Compose interpolation: use the single-quoted values written by `scripts/configure_env.py`, validate without printing resolved secrets, and verify login before enabling the engine. Never paste `docker compose config` output into an issue because it can reveal environment secrets. For Compose backup, pause and stop writers, then use the backup tool against the named volume in a temporary container or copy it only while fully stopped.

## Updates and verification

Keep a recoverable backup, pause entries, stop writers, install a reviewed source revision and dependencies, apply migrations, run the test suite/security audit, start the backend and perform a paused reconciliation. Monitor a full quarter-hour cycle before resuming. ARM64 package availability and the target VM/systemd/Caddy configuration require verification on that host. This repository supplies deployment configuration; it does not claim a cloud deployment happened without cloud access.

The locked native-library versions were checked against official PyPI wheel metadata for CPython 3.12/AArch64 and Ubuntu 24.04's glibc baseline. All seven checked packages had compatible non-yanked wheels; see [docs/ARM64_COMPATIBILITY.md](docs/ARM64_COMPATIBILITY.md). This establishes artifact availability, not an executed ARM64 installation or benchmark. Run installation, imports, tests, timer/TLS checks and backup recovery on the actual VM before enabling entries.
