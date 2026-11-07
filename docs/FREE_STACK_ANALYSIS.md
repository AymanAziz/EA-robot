# Best zero-cost stack analysis — 2026-11-07

## Decision

The best zero-subscription-cost version of this project is the architecture already selected, with two additions: an external readiness monitor and (optionally) Groq Free used only for research observations.

| Layer | Recommended zero-cost choice | Important boundary |
|---|---|---|
| Authoritative backend | Existing Mac, or preferably an already-owned always-on Linux machine | The host, storage, scheduler and minute monitor stop when the machine sleeps, loses power/Internet or logs out. Electricity and Internet are not free. |
| Public HTTPS | Tailscale Personal + Funnel -> loopback Caddy -> loopback FastAPI | Personal is $0 for personal use, but Funnel is beta and has non-configurable bandwidth limits. |
| Frontend | Streamlit Community Cloud | Frontend only; it can sleep without interrupting the backend. |
| Source control | Existing private GitHub repository | Keep `.env`, database files, keys and generated administrator credentials out of Git. |
| Default market data/execution | Coinbase public crypto data + persistent local simulator | Venue-specific data and simulated fills are research evidence, not broker-paper or live performance. |
| Optional paper brokers | Alpaca Paper; OANDA Practice where the user's OANDA division supports v20 | Credentials remain on the backend. Neither account establishes a profitable strategy. |
| Optional AI | Groq Free, `openai/gpt-oss-120b`, strict JSON schema, research-only strategy | Verify the account tier and returned model catalog first. Never upgrade or attach a paid fallback automatically. |
| External monitoring | UptimeRobot Free against `/readyz` | Detects downtime; it cannot prevent Mac sleep, power loss or network loss. |

This is the best *safe* free version, not the version that trades most often. The current candidate model was correctly rejected, no strategy is approved, and execution should remain disabled.

## Current verified state

Local status was checked on 2026-11-07, followed by a verified backup and a fail-closed historical-data/model experiment:

- Backend: `online: true`, paper mode, persistent simulator, zero open positions and configured account equity unchanged at 10,000.
- Strategy: `quant_only`, execution disabled, no validation certificates.
- Data: BTC/USD and ETH/USD now each have 17,539 genuine contiguous Coinbase candles from 2026-05-08 07:45 UTC through 2026-11-07 00:15 UTC. A requested one-year BTC backfill was refused because Coinbase omitted 25 consecutive intervals during 2026-05-08 01:30–07:30 UTC; no candles were filled or invented. The successful interval begins after that gap.
- Legacy one-hour models: fresh BTC/USD and ETH/USD candidates were trained against the longer data and both remain inactive and rejected. BTC ROC-AUC improved from about 0.447 to 0.537 and its Brier score narrowly beat the class-prior baseline, but it still produced zero validation/test trades and failed seven acceptance gates. ETH ROC-AUC was about 0.512, its Brier score was worse than the class-prior baseline, it produced zero validation/test trades and failed eight gates. Neither candidate was promoted.
- Predeclared twelve-hour models: one policy definition now binds the 48-bar label, 49-bar purge, backtest, model metadata, forward monitoring and durable runtime expiry. Final reviewed-policy candidate `20261107T010000-c5a7be309614` for BTC/USD reached ROC-AUC 0.5689 and Brier 0.25069 versus a 0.25020 class-prior score, produced zero validation/test trades and failed eight gates. Candidate `20261107T010000-ba7d0e053cbc` for ETH/USD reached ROC-AUC 0.5500 and Brier 0.25816 versus 0.25044, produced zero trades and failed eight gates. Three identical training requests per symbol returned the same version, original timestamp and unchanged artifact fingerprint; two saved-model backtests per symbol were byte-identical. Both candidates remain inactive.
- Live policy: `PT_HOLDING_HORIZON_BARS=48`; crypto remains enabled, equities/forex are disabled because their sessions cannot safely contain this global horizon, and the 01:00 UTC post-restart scheduler cycle completed successfully with zero orders. Strategy execution and AI remain disabled.
- AI: disabled, no configured model, no requests or tokens used, and the account tier is unverified.
- External alerting: the public `/readyz` endpoint is healthy, but the UptimeRobot monitor and test-alert receipt remain account-bound operator steps; they are not claimed as configured.

Those results do **not** justify lowering thresholds, promoting either candidate, or using AI to manufacture entries. `NO TRADE` is the correct outcome until a revised hypothesis earns support from untouched chronological evidence and passes the existing gates.

The one-hour zero-trade result is economically unsurprising. In the new sample, the average positive one-hour label move was about 26 basis points for BTC and 34 basis points for ETH. The declared crypto decision cost is already 70 basis points before the observed bid/ask spread and the required five-basis-point net edge (two-sided fees and slippage). Even a perfect probability cannot turn the current label's average positive move into sufficient expected net edge. The twelve-hour horizon was therefore registered as a defensible *new hypothesis*, with a new policy version, horizon-sized purges, matching runtime expiry and fail-closed artifact checks. Its first candidates also produced zero qualifying trades. This does not establish predictability, profitability or robustness; only genuinely new forward observations can add evidence now.

The live audit also found a concrete availability limit: on 2026-11-06 the battery-powered Mac slept through most scheduled work. Only 24 of 96 expected quarter-hour slots ran or returned degraded results, and the scheduler logged 42 explicit missed-run warnings. It recovered after AC power was restored and subsequently completed every observed quarter-hour cycle. This makes host uptime—not cloud AI—the first operational priority.

## Why this stack is the strongest free fit

### Backend and HTTPS

Tailscale's Personal plan is advertised as **$0 free forever** for personal use, with up to six users, and Funnel is available on all plans ([Tailscale pricing](https://tailscale.com/pricing), [Funnel documentation](https://tailscale.com/docs/features/tailscale-funnel)). Funnel provides a public `*.ts.net` TLS origin without a purchased domain or router port-forward, but it is still beta, accepts only specified public TLS ports and has bandwidth limits that cannot be configured. It supplies connectivity, not compute: the Mac must remain awake, logged in and online.

If the user is an eligible full-time higher-education student, Azure for Students is the only stronger no-card, off-device option identified: Microsoft documents $100 credit, no credit card, one-year validity and annual renewal while eligibility continues ([Microsoft Learn](https://learn.microsoft.com/azure/education-hub/about-azure-for-students)). It is conditional credit rather than a permanent unconditional server. Oracle Always Free is not a no-card path: Oracle documents credit/debit-card identity verification during signup ([Oracle signup](https://docs.oracle.com/en-us/iaas/Content/GSG/Tasks/signingup_topic-Sign_Up_for_Free_Oracle_Cloud_Promotion.htm)).

### Frontend

Streamlit describes Community Cloud as free and able to deploy from public or private GitHub repositories ([Community Cloud](https://docs.streamlit.io/deploy/streamlit-community-cloud)). It is appropriate only for this lightweight dashboard. Apps with no traffic for 12 hours sleep, and published CPU/memory/storage limits can change; a visit wakes an app ([app resources and hibernation](https://docs.streamlit.io/deploy/streamlit-community-cloud/manage-your-app)). Therefore the scheduler, SQLite ledger, models, credentials and protection monitoring must stay on the persistent backend. Do not ping Streamlit merely to keep it awake.

### Market data and paper execution

Coinbase Exchange's public candle route supports 15-minute buckets without account credentials, but returns at most 300 candles per request and may omit intervals with no ticks ([candles](https://docs.cdp.coinbase.com/api-reference/exchange-api/rest-api/products/get-product-candles)). Its public REST endpoints are limited by IP to 10 requests/second, with bursts up to 15 ([rate limits](https://docs.cdp.coinbase.com/exchange/rest-api/rate-limits)). The ticker reports the venue's last trade and best bid/ask ([ticker](https://docs.cdp.coinbase.com/api-reference/exchange-api/rest-api/products/get-product-ticker)). This makes Coinbase plus the local simulator the lowest-friction research baseline for BTC/USD and ETH/USD, but its results must remain labeled as Coinbase/simulator evidence.

Alpaca Paper is free and globally available as a paper-only account with email signup. Its free stock feed is IEX only, rather than consolidated US-market SIP data, and paper simulation omits market impact, queue position, latency slippage and several other live effects ([paper trading](https://docs.alpaca.markets/us/docs/paper-trading), [market-data plans](https://docs.alpaca.markets/us/docs/about-market-data-api)). It is a useful optional paper venue for the implemented instruments, not a reason to switch to live trading.

OANDA documents a free demo account and v20 API access, including real-time rates and historical prices, but v20 is unavailable in some OANDA divisions ([OANDA v20 introduction](https://developer.oanda.com/rest-live-v20/introduction/)). Treat regional/account eligibility as an operator verification step; do not synthesize forex data or silently substitute another venue.

### Free AI

Within the providers already implemented, Groq Free is the only defensible zero-cost AI path. Groq lists `openai/gpt-oss-120b` as a production model and its featured flagship open-weight model; `openai/gpt-oss-20b` is the lower-cost/faster production alternative ([supported models](https://console.groq.com/docs/models)). Both currently have documented Free Plan limits of 30 requests/minute, 1,000 requests/day, 8,000 tokens/minute and 200,000 tokens/day; exact organization limits remain authoritative in the account console, and limit exhaustion returns HTTP 429 ([rate limits](https://console.groq.com/docs/rate-limits)). Groq supports strict structured output for both models ([structured outputs](https://console.groq.com/docs/structured-outputs)).

The 120B model is the best *starting candidate* for qualitative research because Groq identifies it as the flagship and it has the same documented free-plan request/token limits as the 20B model. That is not evidence that it predicts markets. Before use, the operator must confirm the Groq account is still on Free, create a key privately, run the application's model discovery, and confirm that the model ID is returned and advertises structured output.

The safe research configuration is:

```dotenv
PT_AI_ENABLED=true
PT_AI_PROVIDER=groq
PT_AI_FALLBACK_PROVIDER=none
PT_GROQ_MODEL=openai/gpt-oss-120b
PT_AI_ACCOUNT_TIER=free
PT_AI_ALLOW_PAID=false
PT_AI_RESPONSE_FORMAT=json_schema
PT_AI_MAX_DAILY_REQUESTS=100
PT_AI_MAX_DAILY_TOKENS=100000
PT_STRATEGY=ai_only_research
PT_STRATEGY_EXECUTION_ENABLED=false
```

Keep the key only in the backend's mode-0600 `.env`; do not put it in Streamlit Secrets or Git. The local ceilings deliberately stay below the published free limits and failure/429 must remain `NO TRADE`.

Do not select the current Hermes API adapter for a zero-cost deployment. Nous now describes its free Portal plan as free-model access for Hermes Agent, while API keys use pay-as-you-go credits and the free plan carries zero monthly credits ([Nous Portal](https://portal.nousresearch.com/)). The application's Hermes adapter is intentionally blocked without explicit paid-use authorization.

### Uptime detection

Add one external HTTP monitor for the public `/readyz` route, not merely `/healthz`. UptimeRobot documents a no-card $0 plan with 50 monitors and five-minute checks ([Free plan](https://help.uptimerobot.com/en/articles/11604710-who-should-use-uptimerobot-s-free-plan)). A non-200 readiness response should alert the operator that scheduling observations are stale or the backend is unavailable. It must not automatically enable trading, relax freshness limits or replay missed opportunities.

## Recommended order of work

1. Keep paper simulator mode and strategy execution disabled.
2. Finish verifying the public Streamlit dashboard, then add an external `/readyz` monitor.
3. Keep the Mac on AC power, logged in, awake with its lid open and online. Prefer an already-owned always-on Linux machine if one is available.
4. Treat the completed six-month backfill and rejected one-hour and twelve-hour candidates as evidence against both hypotheses, not as permission to tune repeatedly on the same holdout. Freeze the policy and collect untouched forward data before another model experiment.
5. Keep the bounded daily-status read model and installed daily backup/log-rotation LaunchAgent under test. It retains seven verified generations and records atomic success/failure status; coordinated pre-change backups still require stopping writers.
6. If qualitative AI research is wanted, create a Groq Free account and validate `openai/gpt-oss-120b` in `ai_only_research` mode. Collect forward observations; do not infer historical LLM decisions.
7. Add Alpaca Paper and OANDA Practice only if their account setup succeeds and venue-specific data/execution are useful. Keep each performance source separate.
8. Consider Azure for Students only if eligibility is confirmed. Do not choose a sleeping/ephemeral free web host for the authoritative SQLite ledger or protection worker.

## Verifiable improvement tickets

These are deliberately separate from strategy activation:

1. **Bounded status read model.** `/status` must return the same documented performance fields while query work grows by days/trades rather than by every minute-level snapshot. A regression test must compare known metrics and prove the status path does not load all snapshot/fill ORM rows.
2. **Backend-neutral UI and runbooks.** Community Cloud errors and security/AI documentation must say “persistent backend host,” with Oracle and the Tailscale Mac listed as concrete deployments. No credential may be moved into Streamlit.
3. **Recurring recovery.** A daily job must create integrity-checked backups, apply an explicit retention policy, record failures, and have a tested restore procedure. Log rotation must preserve recent diagnostics without unbounded growth.
4. **External readiness alert.** A free external monitor must check the public `/readyz` route and successfully deliver one test alert. It must never change controls or replay missed jobs.
5. **Public-login hardening.** Failed-login state must be bounded and survive an API restart, without trusting arbitrary forwarded client IPs. Store the generated password in a password manager, then remove the plaintext bootstrap file.
6. **Strategy-research reset.** Write a new economic hypothesis whose expected move can plausibly exceed conservative round-trip costs, register the development and untouched evaluation periods before training, and retain `NO TRADE` unless every existing acceptance gate passes.

## Meaning of “free”

This recommendation targets RM0 in mandatory software/service subscriptions and avoids entering a payment card. It does not eliminate electricity, existing Internet service, hardware wear, account availability, regional eligibility, quota changes or provider outages. Free tiers can change; re-check the cited first-party pages and each account console before enabling any external integration.
