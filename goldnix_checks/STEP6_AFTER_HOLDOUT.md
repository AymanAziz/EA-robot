# Step 6 after the completed Step 7 diagnostic

Checked on 2026-11-12. Step 7 completed once, with both versions passing its
collapse criterion. Step 6 remains unapproved. The audit re-evaluated the
original G1–G9 rules against authenticated, corrected Step 6 statistics and
reproduced every stored gate outcome exactly. No strategy, threshold, account
balance, bootstrap seed or historical result was changed.

Machine-readable audit: [step6_after_holdout.json](out/step6_after_holdout.json).
Completed holdout: [Step 7 report](../goldnix_step7/out/REPORT.md).

## Remaining failures

| Gate | V1 | V2 | Requirement |
| --- | ---: | ---: | --- |
| G1: lower confidence bound of mean R | -0.096424 | -0.061685 | > 0 |
| G2: signal minus random baseline | +0.099433 | +0.112954 (PASS) | >= +0.10R |
| G4: positive eras | 0/4 | 2/4 | >= 3/4 |
| G5: completed baskets | 1,734 (PASS) | 677 | >= 1,000 |
| G7: annual p99 dollar drawdown | $160.21 | $90.67 | <= $2.40 |

Both versions already pass corrected G3, G6, G8 and G9. The older V3 research
note and broker report describe a baseline defect and a failed V2 G3 from
before the corrected Step 6 revision. That defect has been fixed and G3 now
passes; it is not an outstanding repair that could unlock approval.

V1 remains `NOT_TRADEABLE_AT_THIS_ACCOUNT_SIZE`. V2 remains
`INSUFFICIENT_DATA`, also failing G1/G4/G7. Step 7 asks whether results collapsed;
it does not establish positive expected returns or override these gates.

## Account constraint

The existing qualification snapshot, dated 2026-11-10, records a $20 account,
a 1 oz minimum XAUUSD exposure and $41.17 minimum required margin. It is a
dated observation, not a fresh account check. Even disregarding that margin
shortfall, the measured drawdown is 66.75 times the $2.40 limit for V1 and
37.78 times the limit for V2.

Conditionally rescaling the existing P/L distributions would require exposure
no greater than 0.014980 oz for V1 or 0.026468 oz for V2. These are arithmetic
screens, assuming unchanged returns and proportionate costs. They are not
broker-qualified sizes or evidence that a new venue passes. On a 100 oz
standard contract, both imply volumes below the verified 0.01-lot minimum.
Reducing exposure alone cannot change mean R, its confidence bound, era
consistency or basket count.

A potential instrument to investigate is XAUUSDc: the provider currently lists
gold on its cent account with cent-lot conventions. This is a documentation
lead only; no account has been qualified or selected.
[Official Standard Cent specification](https://get.exness.help/hc/en-us/articles/17537782786588-Standard-Cent-account).

The actual minimum volume, volume step, contract size and tick values must be
read from the intended account's symbol properties. The existing
`ExportQualification.mq5` and `qualification.py` provide a read-only starting
point. Historical target-venue bid/ask data, commissions and financing terms
are also needed; advertised minimum spread does not establish realized costs.
[Official MT5 symbol properties](https://www.mql5.com/en/docs/constants/environment_state/marketinfoconstants).

## Work needed for a new attempt

1. Resolve the venue constraint while keeping the verified $20 budget. The
   user has been asked whether the current broker is mandatory or a smaller
   gold contract may be investigated. No funding or account creation is assumed.
2. Qualify a concrete account's exposure and costs before assigning it a
   risk-pass claim. The existing source cannot supply target-venue costs.
3. Define a separate strategy revision and its trial budget. G1 needs a
   stronger net effect; G4 needs consistency; V2's hard H4 filter also leaves
   it 323 baskets short. Changing that filter is a new strategy hypothesis,
   not a correction to the frozen V2 result. Its success is unknown.
4. Register the revised evaluation before testing. Existing 2005–2025 results
   have already influenced design. The 2026 annual file was opened for Step 7;
   its January–September outcomes are now known and cannot become an untouched
   holdout for a tuned replacement. Another same-history pass would be an
   exploratory result, with the prior trials disclosed. A new validation
   window must be defined and reserved for independent confirmation.

No parameter search or new holdout evaluation was performed in this audit.
All existing freezes and Step 7 artifact hashes verified. Step 8 remains
unavailable for both frozen versions. Passing a future revision cannot be
guaranteed before its evidence exists.
