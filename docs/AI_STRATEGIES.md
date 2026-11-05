# Quantitative and AI strategy validation

The existing calibrated LightGBM model, `decide()` function, risk approval and paper broker adapters retain their roles. Cloud AI provides a bounded interpretation of supplied market evidence. Its confidence is an uncalibrated opinion and is never averaged with an ML probability or used as a position size.

| Strategy | Entry rule | Missing, stale or disagreeing AI |
|---|---|---|
| `quant_only` | Existing validated LightGBM decision; explicit execution opt-in | Does not depend on AI |
| `ai_filtered_quant` | Quantitative BUY plus timely AI BUY/long in bullish/ranging conditions with non-high opinion risk; approved strategy validation required | HOLD |
| `hybrid` | Quantitative BUY plus timely AI BUY/long, low opinion risk and bullish conditions; approved strategy validation required | HOLD |
| `ai_only_research` | Recommendations recorded for research; no automatic entries | No execution |

These are declared research hypotheses, not claims of improved returns. The stricter hybrid rule is deliberately explicit; it has no arbitrary weighted-confidence formula. Both AI-assisted strategies must demonstrate their own incremental value before being enabled. The AI cannot turn a quantitative HOLD into BUY, cannot bypass risk approval, and cannot veto an existing quantitative CLOSE/SELL or the independent stop, kill, circuit and holding-horizon monitors. This preserves reductions of previously opened paper positions even while new entries are disabled.

## Explicit activation

Fresh configuration defaults to `PT_STRATEGY=quant_only` and `PT_STRATEGY_EXECUTION_ENABLED=false`. To use quant-only paper execution, an operator must first promote an independently accepted quantitative model and explicitly set `PT_STRATEGY_EXECUTION_ENABLED=true`. AI availability never silently switches a configured AI-dependent strategy back to quant-only.

An AI-assisted entry additionally requires an accepted, explicitly approved certificate matching its symbol, quantitative model version, AI provider, AI model, current strategy/risk policy and expiry. A candidate being accepted does not automatically approve it. Certificates include integrity hashes for both the candidate and its underlying report. Approval is a trusted local administrator operation, not an AI response field or a public trading-control route. Changing policy source, costs, risk configuration, model or provider invalidates the approval; it does not rewrite any earlier records.

## Comparison from genuine observations

The trading engine stores forward observations of the actual quantitative prediction, its decision time, the AI analysis that was available, its provider/model and original timestamps, and the fused decision. Comparing strategies never calls today's LLM on old candles and represents the answer as a historical forecast.

The `compare-strategies` command enriches these observations from the quantitative model's immutable metadata and runs the existing backtest with the same costs, calendars, causal features and risk approval. It requires:

- One quantitative model version and its original frozen probability threshold.
- Model acceptance, training timestamp and complete data-end provenance. An observation must occur after that candidate's entire research dataset and after the model existed.
- Genuine `forward_observation` rows from one execution venue. Simulator observations and broker-paper observations are kept separate.
- Candle completion before the recorded decision, a decision within the configured scheduling window represented here by sixty seconds, and a fully observed forward outcome.
- Timely, matching AI identity and a response available before the modeled execution. The replay assumes next-bar-open fills; AI finishing after that open cannot receive historical entry credit, even if a real second-twenty market order could later have used it.

Missing AI is retained as missing. It vetoes only AI-dependent entries while the same quantitative observation remains in the benchmark. The comparison therefore cannot improve the AI result by silently deleting outage or disagreement periods. Quantitative reducing exits remain unchanged. The rule benchmark uses the same observed decision grid, and buy-and-hold uses the same maximum capital allocation.

The chronological first sixty percent is the validation partition; the last forty percent is the test partition. A holding-horizon purge prevents validation outcomes overlapping the test. No weights, thresholds or AI prompts are tuned on those test results. There must be at least ten matured usable rows to produce a comparison report; acceptance is substantially stricter.

Default acceptance gates require the configured minimum forward observations and closed trades in both partitions, positive net returns after estimated costs, positive Sharpe, profit factor above one, drawdown within the configured limit and a positive lower block-bootstrap mean P/L diagnostic. AI strategies must also improve on quant-only in both partitions and exceed the rule and capped buy-and-hold test benchmarks. Insufficient data and failed gates are valid NO TRADE outcomes. A block bootstrap is an approximate diagnostic, not evidence that future profits are guaranteed.

## Commands

Run from the existing repository/virtual environment, after collecting genuine forward observations:

```bash
papertrade compare-strategies 'BTC/USD'
```

The command writes a labeled report and unapproved candidate validation records. After reviewing a candidate that actually passed every gate:

```bash
papertrade approve-strategy CANDIDATE_ID
```

Then select the corresponding strategy in the engine's private environment, enable paper strategy execution and restart its supervised process:

```dotenv
PT_STRATEGY=ai_filtered_quant
PT_STRATEGY_EXECUTION_ENABLED=true
```

Changing the environment is an operator deployment action; the dashboard has no live-trading toggle. Paper orders still require the independently accepted quantitative model, fresh data, current AI/certificate where applicable, authenticated operational state and final risk approval. Do not delete an existing database, fills or unresolved intents to force activation.

## Reading the results

`forward_replay` means an estimated historical replay of timestamped forward observations. It is not an actual simulator fill and is not an Alpaca/OANDA fill. Research metrics are labeled with that source, interval, assumptions and venue provenance. The actual paper account's equity, orders and fills remain in their existing dashboard views. An AI-only opinion has no validated expected-return execution model, so its research view has recommendation observations and unavailable performance metrics rather than invented P/L.

Free OHLCV bars do not establish the exact spread, queue or fill price at a second-twenty decision. Estimated next-open fills, slippage and stop-first OHLC paths remain approximations. Each comparison uses one symbol in isolation; the operational portfolio can additionally reject combined/correlated exposure. Reusing the same acceptance period does not create a new untouched test. The system must accumulate real future observations after changes, and broker-hosted forward paper results remain a separate operational check.
