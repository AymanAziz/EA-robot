# XAU/USD free double-test result

Run on 2026-11-07 using the preregistered research-only workflow. No broker
credential was read, no order was sent, and XAU/USD was not enabled in the
trading engine.

## Verdict

**Inconclusive. The run did not prove a trade win rate above 50%.** The frozen
strategy selected a 0.60 probability threshold on development data, then
generated zero qualifying trades in both untouched chronological tests. A zero
trade result has no win rate and cannot authorize a paper or live order.

| Test | Provider-clock interval | Closed trades | Win rate | Wilson 95% lower bound | After-cost P/L | Status |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| A | 2026-04-10 13:00 to 2026-07-22 14:00 | 0 | N/A | N/A | USD 0.00 | Inconclusive |
| B | 2026-07-22 15:30 to 2026-10-30 19:30 | 0 | N/A | N/A | USD 0.00 | Inconclusive |

The minimum evidence gate was 200 non-overlapping closed trades in **each**
test. Passing also required a point win rate above 50%, a Wilson 95% lower
confidence bound above 50%, positive return after costs, profit factor above
one, positive provider-bar Sharpe, maximum drawdown no worse than -10%, a
positive bootstrap lower mean trade P/L, and both benchmark gates.

## Locked inputs and costs

- Requested source interval: 2024-01-01 through 2026-10-30.
- Accepted rows: 67,017 M15 bars in 52 capped requests.
- Source label: unidentified “Exness-style” MT5 feed from AlgoSpecial; not
  OANDA and not a broker fill feed.
- Provider timestamps were kept as unknown broker-server time, never relabelled
  UTC; clock/session features were excluded.
- One full reported spread was charged at entry and again at exit, plus 2 bps
  slippage per side and 1 bp commission per side.
- Development-only 99th-percentile spread fallback: USD 0.364.
- Frozen model SHA-256:
  `70cbcf6cc862b503239496516b697420011678777dcf4ef03e94890938de9826`.
- Frozen threshold SHA-256:
  `916464c13122590effc5c83d018b712d51ee2225af13982f5be54578c32ea005`.
- Prepared data SHA-256:
  `57e685ea3e53ceb59c4e4024b5885ce5a984cb18e4cd5ec4b99042c30856b75e`.

## Reproduction

The initial execution and three cache-only reruns produced identical report
bytes:

```text
75f45f5e280a14cdf3c8f57f21348e6c3e769801529b0008e2b2a17354d149bb
```

This proves deterministic reproduction of this historical calculation only.
It is not four independent market tests and is not evidence of future
profitability. The full local evidence is in
`var/gold_research/xauusd_m15_20240101_20261030_report.json`; the private raw
history cache remains ignored by Git.

## Decision

No trade was placed. Placing one after this result would contradict the locked
evidence contract: the strategy supplied no qualifying signal and neither test
met the minimum trade count. A genuine next-stage test requires a supported
broker Practice feed and fresh, untouched quotes/fills; it cannot be honestly
manufactured from repeated historical runs.

Source and licensing limitations are documented in
[GOLD_FREE_DATA_RESEARCH.md](GOLD_FREE_DATA_RESEARCH.md). The stronger OANDA
Practice evidence contract is documented in [GOLD_RESEARCH.md](GOLD_RESEARCH.md).
