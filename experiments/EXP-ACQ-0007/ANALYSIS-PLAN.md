# EXP-ACQ-0007 — analysis plan

Frozen with `PREREGISTRATION.md` on 2026-09-16, before any message existed. Anything not written
here is a deviation and is recorded as one.

## The analysis is a single call to AGE's own evaluator

No bespoke statistics. The comparison runs through the procedure evaluator that already governs
every procedure claim in this repository, with both sides inside one experiment:

```
experiment        EXP-ACQ-0007
candidate arm     candidate   -> marketingskills_cold_email@2.0.0
baseline arm      baseline    -> theplus.outreach-research@1.0.0
use case          message_generation
primary metric    qualified_reply_rate
```

The evaluator supplies the result class, the decision and the reason. This document does not
restate its rules; it records the choices that are ours to make and that must be fixed in advance.

## Counting

- **Unit:** one account = one exposure. One message per account. A second contact at the same
  account is not a second observation.
- **Denominator:** matured delivered exposures. An exposure matures 14 days after delivery
  (`EVIDENCE_POLICY["response_window_days"]`). Undelivered and unmatured exposures are excluded
  from the denominator, not counted as non-replies.
- **Numerator:** `qualified_replies`, per AGE's existing reply-decision records. A reply is
  classified by the same process used by `EXP-ACQ-0001`; this experiment introduces no new
  classification rule.
- **Bounces** are recorded as `message_bounced` and reduce the denominator. See the no-slack note
  in the preregistration: they can take the comparison below the 30-per-side floor.

## Timing

- Both arms send **concurrently**. Non-concurrent arms are a competing variable and the evaluator
  will return `CONFOUNDED`.
- The analysis runs **once**, after the last exposure in both arms has matured. No interim looks,
  no early stopping, no peeking at the split before that point.
- If either arm is still maturing, the evaluator returns `IMMATURE` and nothing is concluded.

## Covariates

The covariates in `cohort.csv` are **reported alongside the result and not adjusted for**. No
covariate-adjusted estimate, no stratified re-analysis, no subgroup claim. With 30 per arm a
subgroup comparison has no power and would be a fishing expedition; the covariates exist so that a
reader can see what the draw produced, including that both caution-flagged accounts landed in
`baseline`.

## Stopping rule

There is no adaptive stopping. The experiment ends when every exposure has matured or when the
founder halts it. A halt before that point yields `NEED_MORE_DATA`, never a verdict.

## What would invalidate the result

Any of these is recorded and the comparison is reported as confounded or unevaluable rather than
repaired:

- an account contacted outside its assigned arm, or contacted twice
- a message altered after generation by anything other than the arm's own procedure
- the candidate procedure exercised outside `message_generation` — sequencing, volume guidance,
  autonomous sending, or ungrounded personalisation
- any input that differs between the arms other than the procedure
- an exposure predating the 2026-09-16T12:03:34+00:00 binding
- synthetic or simulated data anywhere in either arm

## Deviations

A deviation is appended to this file with its date, what changed and why, before the analysis runs.
The preregistered text above is never edited in place.
