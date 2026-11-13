# Current EA source snapshot

The active demo implementation is `goldnix_auto_m1/GoldnixAutoM1.mq5` version1.20:
closed M1 channel20 BUY/SELL entries, one0.01lot position, a5USC planned-risk cap,
and persistent profit protection. Profit protection arms after the declared
threshold, tightens SL toward half the observed executable profit peak, and
requests an early close when that floor is breached. Entry/exit quotes use the
correct Bid/Ask sides. This is not a guarantee of retaining profit through gaps.

`goldnix_p01` contains an independent quote/timer replay, native tester adapter,
data collector/auditor, parity comparison and Step6 statistical diagnostics.
Historical experiments and their executable source are retained in the other
`goldnix_*` packages. Local generated evidence, credentials, terminal settings,
raw quote archives and compiled executables are excluded from this source push.
README links to local run artifacts require those artifacts to be regenerated
or restored from the user's local workspace; source code is preserved here.

The current P01 engineering evidence consists of249 native/reference trade
matches and58,489 signal-decision matches across January/February2024 generated
broker ticks. Formal Step6 has not passed. The updated conservative diagnostic
has mean−0.050252R, bootstrap lower bound−0.102680R and annual IID Monte Carlo
p99 drawdown17.87% of aUSD20 account. These two months do not establish four-era
performance. Full data and a certified matched random baseline are missing.

The user has explicitly required **approval after Step6 before running Step7**.
No subsequent Step7 price access, holdout consumption or evaluation may proceed
without that approval. Previously used2026 history remains consumed.

Run the research tests from the repository root with the project's Python
environment and `PYTHONPATH=goldnix:.`. For the current candidate:

```sh
PYTHONPATH=goldnix:. .venv/bin/pytest -q goldnix_p01/tests goldnix_step6/tests goldnix_step7/tests
```

Native compilation/testing requires the authorized local MT5 installation.
The native replay launcher requires a verified flat demo account, performs a
bounded tester handoff, and restores the normal terminal. Do not run a historical
test adapter on a chart or substitute generated ticks for qualified real history.
