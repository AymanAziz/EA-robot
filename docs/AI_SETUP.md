# Cloud AI setup, operation and validation

Cloud AI extends the existing LightGBM platform. It does not replace training, expected-return/cost checks, risk limits, paper adapters or broker reconciliation. All keys and usage records belong on the Oracle backend, while Streamlit Community Cloud is an authenticated HTTPS frontend. The default configuration makes no provider calls, enables no paid use and opens no new strategy entries.

## Safe default configuration

Keep these values until account access, model compatibility and strategy validation are ready:

```dotenv
PT_MODE=paper
PT_AI_ENABLED=false
PT_AI_PROVIDER=groq
PT_AI_FALLBACK_PROVIDER=none
PT_AI_ACCOUNT_TIER=unverified
PT_AI_ALLOW_PAID=false
PT_GROQ_API_KEY=
PT_GROQ_MODEL=
PT_HERMES_API_KEY=
PT_HERMES_MODEL=
PT_HERMES_BASE_URL=https://inference-api.nousresearch.com/v1
PT_STRATEGY=quant_only
PT_STRATEGY_EXECUTION_ENABLED=false
```

`.env.example` lists the remaining defaults. Pydantic also accepts the requested unprefixed `AI_PROVIDER`, `AI_FALLBACK_PROVIDER`, `GROQ_API_KEY`, `GROQ_MODEL`, `HERMES_API_KEY`, `HERMES_MODEL` and `HERMES_BASE_URL` aliases. Use one spelling per value; the `PT_` form has precedence when both exist. Do not put credentials on a shell command line, in Git, in Streamlit Community Cloud Secrets, or in an issue/screenshot. Edit the VM's protected `.env` privately and restart the relevant supervised process after configuration changes.

## Groq: default provider

1. Create or use an API account in the official [Groq console](https://console.groq.com). Confirm its actual plan, enabled billing, accessible models and account-specific limits.
2. Store its API key as `PT_GROQ_API_KEY` on the VM. Set `PT_AI_ACCOUNT_TIER=free` only after verifying a free account; this is an operator assertion, not an API-provided billing guarantee. Keep `PT_AI_ALLOW_PAID=false`.
3. Discover the account-visible model catalog:

```bash
cd /opt/papertrade
sudo -u papertrade .venv/bin/papertrade ai-models --provider groq
```

4. Copy an actually returned supported ID into `PT_GROQ_MODEL`. No model ID is selected automatically. Check that model's current [structured-output support](https://console.groq.com/docs/structured-outputs), context limit and [rate limits](https://console.groq.com/docs/rate-limits).
5. Set `PT_AI_ENABLED=true` when analysis calls are desired. This enables analysis only; it does not enable a strategy or authorize paid calls.

```bash
sudo -u papertrade .venv/bin/papertrade ai-status
sudo -u papertrade .venv/bin/papertrade run-once
sudo -u papertrade .venv/bin/papertrade analyze-ai
sudo -u papertrade .venv/bin/papertrade ai-status
```

The analysis requires fresh stored completed candles and a genuine current prediction from a validated active LightGBM model. If none exists, the correct result is skipped/disabled rather than fabricated market analysis. Model discovery can run before a model ID is selected; discovery is a real metered HTTP operation, not a successful completion or trading certification.

The adapter uses the documented `https://api.groq.com/openai/v1/models` and `/chat/completions` routes. JSON Object mode is the compatibility default with independent strict Pydantic/evidence validation. Set `PT_AI_RESPONSE_FORMAT=json_schema` only for a model/account whose current support you have verified. Unsupported format/model responses fail safely; there is no automatic switch to a new model, format, tier or provider.

Groq has no free-only billing-enforcement parameter implemented by this application. The software cannot determine an organization's current subscription, other applications' usage or a price change from a successful API response. Confirm plan restrictions in the provider console and set provider-side spending limits where available. Defaults and local quotas are not a promise of RM0 API usage.

## Optional Nous Hermes

Nous Hermes is an alternative, not a fallback. Verify current account access and billing using the official [Nous Portal](https://portal.nousresearch.com/api-docs) and [integration documentation](https://hermes-agent.nousresearch.com/docs/integrations/nous-portal). Its free availability is not assumed. Do not enable paid calls without explicit authorization.

For an authorized account, privately configure:

```dotenv
PT_AI_PROVIDER=hermes
PT_HERMES_API_KEY=
PT_HERMES_MODEL=
PT_HERMES_BASE_URL=https://inference-api.nousresearch.com/v1
PT_AI_ACCOUNT_TIER=paid
PT_AI_ALLOW_PAID=false
```

The example deliberately leaves paid use blocked. Only after explicit paid authorization may `PT_AI_ALLOW_PAID` be changed to `true`. Then use `papertrade ai-models --provider hermes`, select an actually available model, and enable analysis deliberately. The adapter accepts only the verified Nous HTTPS origin, never arbitrary hosts, redirects, local endpoints or user-provided tools. Switching provider/model invalidates incompatible AI evidence and strategy approval; it does not activate a paid fallback. With absent credentials/access/authorization, Hermes remains disabled.

## Analysis evidence and untrusted responses

The worker sends a bounded, structured context: symbol/asset class and evidence timestamp, completed candles, current observed price, trend/momentum/volatility/volume measures, support/resistance estimates, LightGBM output, regime and current stored positions. No verified news/macro source is integrated by default, and the context explicitly says so. Do not market that absence as neutral news sentiment.

The model is asked for bullish/bearish evidence, liquidity/volatility risks, quant agreement, risk factors, reasons to avoid entry and a conservative recommendation. The response must match the exact symbol/evidence timestamp and declared enum/schema. Invalid JSON, duplicate keys, missing fields, stale/future/contradictory output, unknown actions, nonfinite confidence, numerical narrative price claims, markup/code/tool attempts and other unsupported content are rejected. Qualitative analysis can still be wrong; validation constrains it rather than establishing truth. No model output gets a broker/client, shell, SQL connection or executable tool.

LLM confidence is an uncalibrated opinion, never a replacement for the LightGBM probability or a weighting input. The risk engine always retains final authority over broker orders.

## Strategy modes and comparisons

| Strategy | Entry rule | Activation requirement |
|---|---|---|
| `quant_only` | Existing quant decision and independent risk checks | Accepted/promoted quant model plus explicit strategy execution flag |
| `ai_filtered_quant` | Quant BUY with timely validated AI BUY/long agreement and permitted regime/risk | Quant requirements plus a current approved AI-strategy certificate |
| `hybrid` | Same agreement with stricter bullish/low-risk evidence | Independent validated/approved hybrid certificate |
| `ai_only_research` | Recommendation records only | Automatic execution always disabled |

AI cannot turn quant HOLD into a BUY, increase risk limits, suppress emergency/protective exits or invent an expected return. AI-dependent entries HOLD when analysis is missing, invalid, stale, disagrees or the provider/budget is unavailable. There is no automatic downgrade to quant-only. Quant-only is available only when independently validated and explicitly selected/enabled.

Forward research observations accumulate without enabling orders. Compare after enough genuine timestamped evidence and subsequent observed market outcomes exist:

```bash
papertrade compare-strategies 'BTC/USD'
```

The stored comparison uses fixed chronological validation/test splits, realistic estimated costs and the same decision/risk semantics, compares quant-only/AI-filtered/hybrid against rule and capped buy-and-hold benchmarks, and records failure reasons. AI variants also need enough timely agreeing observations and improvements over quant-only in both partitions. Positive net returns, minimum closed trades, drawdown limits, Sharpe/profit-factor and a block-bootstrap lower-mean-P/L gate can all reject a strategy. Reusing a holdout is not a fresh test. Historical LLM calls are not fabricated: a replay only uses AI/predictions that were actually available at the original decision time.

Reports are labeled **`forward_replay`: estimated execution on timestamped forward observations**, not actual broker-paper returns. The dashboard keeps sources separate. Actual fills/account equity remain the execution record, and no figures exist before sufficient evidence.

An operator can explicitly approve only a passing, current stored validation:

```bash
papertrade approve-strategy VALIDATION_ID_FROM_COMPARISON
```

Then select the corresponding strategy and deliberately set `PT_STRATEGY_EXECUTION_ENABLED=true`. Approval is a strategy deployment action; supported subsequent paper orders require no human approval. Certificates bind symbol, quant/AI versions, provider, policy, report provenance and expiry; mismatches/changes require new validation. No certificate can enable live trading. If no strategy passes, keep **NO TRADE**.

## Usage, cache and outage policy

```dotenv
PT_TRADING_INTERVAL_MINUTES=15
PT_AI_ANALYSIS_INTERVAL_MINUTES=60
PT_AI_MAX_DAILY_REQUESTS=100
PT_AI_MAX_DAILY_TOKENS=100000
PT_AI_MAX_OUTPUT_TOKENS=512
PT_AI_TIMEOUT_SECONDS=8
PT_AI_MAX_ATTEMPTS=2
PT_AI_MAX_AGE_MINUTES=75
```

The quant engine still runs every fifteen minutes, and protection runs every minute. The AI worker wakes after each quant cycle to inspect gates, normally reuses unchanged valid context for an hour, and allows configured material state/probability/price/volatility changes to trigger a new request after a minimum interval. It does not call the LLM for every symbol every quarter-hour. There is no undocumented synchronous batch request or shared cross-symbol recommendation: shared absent news/macro context is explicit, and every symbol is validated independently.

Every actual HTTP attempt, including retries and `/models` discovery, consumes a durable request reservation across all processes/providers. Generations reserve a conservative prompt/output-token amount before network I/O. Known reported usage settles it; unknown timeout/crash usage remains conservatively charged. Local counters reset by UTC day. Account-wide requests from other applications are outside these counters.

HTTP 429 records rate-limit headers; bounded exponential backoff respects numeric Retry-After within the configured delay ceiling. Retries cannot exceed the configured attempt count or remaining daily budget. Provider downtime/invalid output/budget exhaustion leaves no usable new AI observation and never creates a fake success or paid fallback. Cache entries expire and are invalidated by relevant context/model/provider changes. The execution path reads durable results and does not wait for slow reasoning HTTP calls.

The default six-symbol workload may hit the 100-request ceiling before a full day, especially with discovery or event retries. That is a deliberate cost cap, not a reason to increase the budget automatically. Reduce symbols/frequency or keep HOLD until the next UTC budget period.

## Monitoring and troubleshooting

```bash
papertrade ai-status
sudo journalctl -u papertrade-ai.service --since today -o cat
sudo systemctl status papertrade-ai.service papertrade-ai.timer
```

Use **AI analysis** for actual model/recommendation/reasons, latency, token usage, failures and rate limits. **Strategy comparison** separates backtest/replay/research/account sources. **System health** shows current scheduler, brokers, Groq/Hermes, database/reconciliation and actual host metrics. Provider connectivity is unknown until checked; configured credentials alone do not mean connected.

- Missing key/model or unverified tier: configure verified access; do not paste keys into chat or disable the guard.
- Missing quant model/current prediction: collect/train/validate/promote first. A failed candidate means NO TRADE.
- Unsupported model/structured format: discover the catalog and check current provider documentation; do not guess IDs.
- HTTP 429/budget exhaustion: inspect actual account and local limits, reduce frequency/output size, and wait for recovery. No paid fallback occurs.
- Rejected schema/evidence: inspect sanitized errors and context provenance; never relax risk because a narrative sounds persuasive.
- No comparison yet: genuine forward observations/outcomes need time to accumulate. Today’s LLM cannot reconstruct yesterday’s available opinion.

Current implementation checks use mocks for authenticated Groq/Hermes contracts. Real provider access, model compatibility, plan/billing controls, Oracle/systemd/ARM64 deployment, public TLS and Community Cloud publication need the user's accounts and deployment environment. They are not claimed verified by mocked tests. Primary provider sources are collected in [AI_PROVIDER_SOURCES.md](AI_PROVIDER_SOURCES.md).
