# Cloud AI provider contracts and limits

Official documentation checked on 2026-11-05. The implementation uses existing `httpx` and Pydantic dependencies; neither an agent runtime nor a local large language model is installed.

## Groq

- [API reference](https://console.groq.com/docs/api-reference): the adapter uses `GET https://api.groq.com/openai/v1/models` for discovery and `POST https://api.groq.com/openai/v1/chat/completions` for analysis, with bearer authentication. `GROQ_MODEL` must be configured and present in the fetched catalog. No example model ID is silently selected.
- [Structured output documentation](https://console.groq.com/docs/structured-outputs): JSON Object mode is the compatibility default; Pydantic still independently validates every field and market-evidence relationship. JSON Schema strict mode is configurable for a model whose provider/account supports it. A schema/compatibility rejection disables that request rather than automatically changing models or formats.
- [Rate limits](https://console.groq.com/docs/rate-limits): limit headers and HTTP 429 are recorded. Retries are bounded to three attempts, use exponential delay, and honor numeric Retry-After up to a five-second per-delay ceiling. The worker's durable callback meters each real attempt, including model-discovery requests; metadata discovery reserves no generation tokens.

The provider API has no free-only billing switch implemented here. The worker must require an explicitly declared free account or authorized paid use. Configured local budgets are conservative operating ceilings, not proof of a provider's free allowance. Users must confirm their actual account plan, model access and limits in the Groq console. No Groq credentials were present during implementation, so no authenticated Groq call or financial recommendation was externally verified.

## Optional Nous Hermes

- [Nous Portal API documentation](https://portal.nousresearch.com/api-docs), reached through the official [Nous help page](https://portal.nousresearch.com/help).
- [Official Nous Portal integration documentation](https://hermes-agent.nousresearch.com/docs/integrations/nous-portal) identifies `https://inference-api.nousresearch.com/v1` as the inference base and explains subscription billing. Its model examples can change; the adapter discovers the account-visible catalog rather than hardcoding one.
- The [official Nous API announcement](https://forum.nousresearch.com/t/announcing-the-nous-portal/62) describes API-key access, purchased credits and OpenAI-compatible completion/chat interfaces. This historical announcement does not establish a current free entitlement.

`HermesProvider` uses only the exact verified Nous HTTPS base above, with `/models` and `/chat/completions`. Arbitrary hosts, URL paths, redirects, environment-provided proxies and non-HTTPS URLs are refused. `HERMES_MODEL` and an authorized bearer credential are mandatory for analysis. The caller must explicitly authorize paid usage; Hermes never becomes an automatic fallback. When the catalog advertises supported parameters, incompatible structured-output models are refused. Otherwise an unsupported-format HTTP response fails safely. Actual account/model compatibility remains credential-gated; documentation lookup and mocked contracts do not certify access. The Portal's browser documentation may require an authenticated/JavaScript session; the application does not scrape that session or invent authentication endpoints.

## Validation and threat limits

The cloud model receives a bounded Pydantic market context containing completed candles, numeric indicators, actual positions, calibrated quant output, and explicit statements that verified macro/news context is unavailable. There is no arbitrary external text field or news prompt. The model has no tools, broker objects, code-execution mechanism, SQL access, secrets or control endpoint access.

The output is a frozen Pydantic object with extra fields forbidden. Symbol and original candle-close timestamp must exactly match the evidence. Stale/future timestamps, invalid JSON, duplicate JSON fields, unsupported actions, contradictory direction/regime/action, missing fields, nonfinite/out-of-range confidence, tool attempts, refusal/truncation, numeric price claims, written-out numeric claims and executable/markup content are rejected. LLM confidence remains an uncalibrated opinion and is never substituted for a LightGBM probability. Narrative numeric claims are prohibited altogether; this deliberately favors rejection over attempting to distinguish a hallucinated price from a legitimate quotation. Qualitative reasoning remains untrusted and cannot independently authorize trading.

Usage and latency in provider results are provider-reported when available. Missing/invalid usage stays explicitly unknown; the durable worker retains a conservative reservation instead of recording a fictional zero-token completion. HTTP failures expose a generic status, never response bodies, transport internals or API keys. Neither model discovery nor a valid response is evidence of trading profitability.

The provider unit tests use deterministic mocked HTTP responses and fixture-only keys/model IDs. No real paid provider call was made.
