# Review of corrected Step-6 evaluation

Scope: source changes since `507a1a7`, reviewed before historical evaluation.
The two reviewers worked independently under the code-review workflow.

## Standards

Initial findings:

- A sampler warning could accompany a top-level PASS despite the documented
  fail-closed requirement. Resolved: an unreliable numerical PASS becomes
  `PROVISIONAL_SAMPLER_WARNING`, including in the freeze.
- The recorded commit could differ from working-tree source. Resolved:
  every manifest file must match the recorded commit's blob before execution.
- Nonblocking design observation: the runner combines preparation, evaluation
  and artifact publication. Kept within this scoped correction.

Reviewer follow-up: both high-priority findings resolved. Targeted verification:

```text
.....                                                                    [100%]
5 passed in 0.42s
```

## Spec

Initial findings:

- A single-trade proposal could trap the baseline in one feasible component.
  Resolved: add paired and complete independent schedule proposals. A small
  enumerable two-schedule regression now samples both feasible states.
- Sampler warning did not prevent approval. Resolved as above.
- The edge bound compared against one random baseline path rather than the
  average of the declared draws. Resolved: resample and average baseline draw
  IDs inside each replicate using the same sampled months as the signal.

Reviewer follow-up: all three findings resolved; no remaining high-priority
finding in the follow-up scope. Targeted verification:

```text
3 passed in 0.50s
```

Final review: zero unresolved high-priority findings on either axis; one
nonblocking runner-structure observation. Finite sampler mixing remains a
documented approximation, with diagnostics reported in each study.
