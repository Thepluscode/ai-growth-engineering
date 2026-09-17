# EXP-ACQ-0007 — execution gate

**Status: `PREREGISTERED_BLOCKED`** · dependency: the mature verdict of `EXP-ACQ-0006`

This file adds an execution condition. It does not amend the preregistration: the hypothesis, arms,
cohort, draw, thresholds and analysis plan in `PREREGISTRATION.md`, `ANALYSIS-PLAN.md` and
`AMENDMENT-01-RESERVE-POOL.md` stand exactly as frozen.

## Why

The founder's standing sequence (2026-09-15) is that no demand-generation experiment runs before
`EXP-ACQ-0006` is judged on or after 2026-09-22. `EXP-ACQ-0007` was frozen on 2026-09-16 and its files
do not mention that dependency, so the order existed only in memory and prose.

## What the gate enforces

It is a row in the store's append-only `experiment_gates` ledger, not a note. While it is open, the
store refuses, for `EXP-ACQ-0007`:

- any canonical funnel event (`experiment_blocked`) — no send, invitation, reply or exposure;
- linking a governed outbound message to it;
- activating a campaign for it (a `planned` campaign may still be declared).

There is no batch generator in this repository; the refusals above are where generated messages
would first become execution.

## How it is released

```
age experiment-gate release --experiment-id EXP-ACQ-0007 --depends-on EXP-ACQ-0006 --as-of <date>
```

The release computes `EXP-ACQ-0006`'s own staged verdict from
`experiments/EXP-ACQ-0006/preregistered-gates.json` for that date and is refused while it is
`NOT_READY` — before its window, or before a governed reply check has run after it. A release
records the verdict status it saw. `age experiment-gate show --experiment-id EXP-ACQ-0007` prints the
ledger.

## Review samples

The paired messages in `MESSAGE-REVIEW.md` are **non-exposure review artefacts**: generated for
human quality review, never queued, scheduled or sent, and not part of any sample. Their full text,
which quotes named officers, stays in the private working copy and is not committed.
