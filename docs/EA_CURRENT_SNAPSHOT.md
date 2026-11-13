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

The current P01 engineering evidence consists of 318 native/reference trade
matches and 72,136 signal-decision matches across January, February and
March 1–14, 2024 generated broker ticks. Formal Step 6 has not passed.
The three-window conservative diagnostic has mean −0.036638 R and net −18.90
USC; adding March changes the sample, not the strategy. Four preregistered
higher-timeframe filters failed the improvement screen. Full four-era data
and a certified matched random baseline are missing. See the complete
[Step 6 comparison](../goldnix_p02/README.md), including all failed candidates,
the preceding-history correction and simulated drawdown limits.

The user explicitly authorized Step 7 on November 13, 2026. The subsequent
P01 preflight is blocked by missing qualification, freeze and untouched data;
approval is no longer the missing prerequisite. Previously used 2026 history
remains consumed. The old H01 numerical Step 6 PASS and V1/V2 Step 7 passes
belong to different candidates. See the verified
[qualification history and protection control](GOLDNIX_PASS_LINEAGE_20261113.md).

Run the research tests from the repository root with the project's Python
environment and `PYTHONPATH=goldnix:.`. For the current candidate:

```sh
PYTHONPATH=goldnix:. .venv/bin/pytest -q goldnix_p02/tests goldnix_p01/tests goldnix_step6/tests goldnix_step7/tests
```

Native compilation/testing requires the authorized local MT5 installation.
The native replay launcher requires a verified flat demo account, performs a
bounded tester handoff, and restores the normal terminal. Do not run a historical
test adapter on a chart or substitute generated ticks for qualified real history.
