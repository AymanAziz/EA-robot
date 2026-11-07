# No-card hosting options — 2026-11-05

## Decision

There are two defensible paths without supplying a credit or debit card:

1. **Azure for Students**, if the user is an eligible full-time student, is the best off-device cloud path. Microsoft currently offers $100 credit for 12 months without a credit card. Eligibility requires age 18+, full-time attendance at an accredited degree-granting two- or four-year institution, and verification with the institution's email address ([official offer](https://azure.microsoft.com/en-us/pricing/offers/ms-azr-0170p), [education FAQ](https://learn.microsoft.com/en-us/azure/education-hub/faq)). It can run a normal Ubuntu VM with persistent storage, but it is temporary credit rather than a forever-free server. Resources are decommissioned if the credit ends and the subscription is not upgraded.
2. If that student offer does not apply, keep the backend on an always-on computer the user controls and publish its authenticated API through **Tailscale Funnel**. The existing Mac can do this while it remains powered, awake and online; an old Ubuntu PC or small Linux computer is a better unattended host because this repository already includes systemd units for supervision.

Tailscale's Personal plan is free and [requires no billing details](https://tailscale.com/docs/account/billing/modify-billing). Funnel is available on all plans, creates a public TLS endpoint, and uses a stable name under the tailnet's `ts.net` domain without requiring a purchased domain, a public IP address or router port forwarding ([Funnel requirements and limits](https://tailscale.com/docs/features/tailscale-funnel), [stable Funnel names](https://tailscale.com/docs/reference/examples/funnel)). A Funnel configured with `--bg` resumes after a device or Tailscale restart ([CLI restart behavior](https://tailscale.com/docs/reference/tailscale-cli/funnel)).

This is a network tunnel, not free compute. The host must stay running. The current application requires Python 3.12, native LightGBM dependencies, a continuously running minute monitor and quarter-hour scheduler, and local durable SQLite/model storage. A sleeping or ephemeral service cannot safely provide those properties. The local database and WAL currently occupy only a few MiB, but its correctness depends on one durable local filesystem rather than copying live SQLite files between services.

## Recommended layout

```text
Streamlit Community Cloud
          |
          | HTTPS: stable *.ts.net address
          v
   Tailscale Funnel
          |
          | loopback only
          v
 route-limiting reverse proxy -> FastAPI
                              -> SQLite/models
                              -> scheduler + minute monitor
```

Keep the existing authentication, route allowlist, security headers and request-size limit in front of FastAPI. Do not expose raw Uvicorn directly merely to make Funnel work. Broker and AI credentials remain only on the backend host. The backend stays in paper simulator mode with AI and strategy execution disabled until separately configured and validated.

Operational limits remain material: Funnel is currently beta, only supports TLS on specified public ports, and has non-configurable bandwidth limits. Home power, Internet and host sleep become the uptime boundary. Tailscale's macOS documentation recommends its direct-download variant to avoid the App Store, although its current macOS variant table and Funnel page are not fully consistent about Funnel support; verify the installed variant before depending on it ([macOS variants](https://tailscale.com/docs/concepts/macos-variants), [macOS installation](https://tailscale.com/docs/install/mac)). A Linux spare host avoids that ambiguity and matches the repository's existing deployment tooling.

## Hosted services checked

| Option | Card status | Continuous worker | Durable SQLite | Public HTTPS | Result |
|---|---|---:|---:|---:|---|
| Azure for Students Ubuntu VM | No card for eligible full-time students | Yes, while credit/subscription remains active | Yes, on managed VM disk | Yes, with normal VM networking/tunnel | **Recommended if eligible**; $100/12-month credit, educational-use eligibility and eventual expiry apply |
| Tailscale Funnel + owned hardware | Personal plan needs no billing details | Yes, while host is awake | Yes, on host | Stable `*.ts.net` TLS URL | **Recommended** |
| ngrok Free + owned hardware | Free HTTP/S works without the card verification required for TCP | Yes, while agent and host run | Yes, on host | Static assigned dev domain | Possible fallback; 20,000 HTTP requests and 1 GB egress per month, development interstitial, and agent uptime limits make it weaker ([limits](https://ngrok.com/docs/pricing-limits), [static dev domains](https://ngrok.com/docs/gateway/domains)) |
| Cloudflare Quick Tunnel + owned hardware | No account or domain required | Yes, while process and host run | Yes, on host | Temporary HTTPS URL | Testing only: hostname changes and there is no uptime guarantee ([Quick Tunnel limits](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/)) |
| Cloudflare named/Zero Trust Tunnel | Free plan still asks for payment details during onboarding | Yes, while host runs | Yes, on host | Stable hostname with managed domain | Rejected by the no-card requirement ([Zero Trust onboarding](https://developers.cloudflare.com/cloudflare-one/setup/)) |
| Render Free web service | No payment required for a first free deploy | No; sleeps after 15 idle minutes | No; free filesystem is ephemeral and free services cannot attach disks | Yes | Incompatible. Restarts/spin-down lose SQLite; free Postgres expires after 30 days ([free service limits](https://render.com/docs/free), [first deploy](https://render.com/docs/your-first-deploy)) |
| Koyeb Free Instance | Koyeb says it requires a card and a verification hold | No; sleeps after one idle hour | No volumes on Free | Yes | Rejected by card requirement and architecture limits ([billing FAQ](https://www.koyeb.com/docs/faqs/pricing), [Free Instance limits](https://www.koyeb.com/docs/reference/instances)) |
| PythonAnywhere Beginner | Free account available | No scheduled or always-on tasks for new free accounts | Small persistent quota, but insufficient architecture | Yes | Incompatible: 512 MiB disk, 100 CPU seconds, one-month web-app expiry, restricted outbound Internet, and no scheduler/always-on process ([free features](https://help.pythonanywhere.com/pages/FreeAccountsFeatures/), [pricing comparison](https://www.pythonanywhere.com/pricing/)) |
| Hugging Face Spaces Free | Free compute tier exists | No; free Spaces sleep | No; local disk is ephemeral | Yes | Incompatible without redesign and paid persistent resources ([Space lifecycle](https://huggingface.co/docs/hub/spaces-overview), [storage](https://huggingface.co/docs/hub/spaces-storage)) |
| Northflank Sandbox | Current pricing page says no card and always-on, but billing docs still say all users must add a payment method | Advertised as always-on | Advertised persistence | Yes | Do not recommend: official terms conflict, and its current status notice says to assume all environment variables were compromised in a November 2026 control-plane security incident ([pricing](https://northflank.com/pricing), [conflicting billing docs](https://northflank.com/docs/v1/application/billing/pricing-on-northflank), [incident notice](https://status.northflank.com/history/1)) |

Render or another sleeping web host cannot be made safe by periodically pinging it: that does not add a durable local disk, independent minute monitoring, reliable process supervision or restart-safe execution. Moving the ledger to a hosted database would also be a substantial redesign because this release deliberately accepts only local SQLite.

## What is needed from the user

Only one eligibility question and, if necessary, one host decision are needed before implementation:

1. Is the user currently an eligible full-time student with a university/college email? If yes, assess Azure for Students first.
2. Otherwise, use the current Mac and accept that it must remain awake and online, or use an old/spare computer that can stay on, preferably Ubuntu 24.04.

No domain, public IP, port-forwarding rule or payment card is needed for the Tailscale path. The user should never send a Tailscale login, private key, backend password, broker credential or AI key. Once the host is chosen, setup can proceed one human step at a time: create a free Personal tailnet with an existing GitHub/Google/Apple/Microsoft identity, install the appropriate client, enable Funnel, capture the public HTTPS URL, supervise the backend processes, then place only that URL in Streamlit Community Cloud Secrets.
