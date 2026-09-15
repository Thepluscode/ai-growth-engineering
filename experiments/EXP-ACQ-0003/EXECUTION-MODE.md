# EXP-ACQ-0003 — execution mode

**Recorded:** 2026-09-15 · **Decided by:** founder

```
EXP-ACQ-0003_EXECUTION_MODE = DESCRIPTIVE_FROZEN_COHORT
```

## Why

`PREREGISTRATION.md` set a minimum sample of 51 standard invitations. The frozen cohort
(`EXECUTION-COHORT.md`) holds 39 people. Reaching 51 would mean changing the population after
the freeze, so the original decision rule cannot be satisfied cleanly.

This does **not** invalidate execution. The preregistration, the cohort and the treatment stay
exactly as frozen; nothing in them is rewritten.

## Rules for the rest of this experiment

- Execute only the 39 frozen buyers. No replacements, no new sourcing, no change to offer,
  invitation (standard, no note), ICP or design, no rerandomisation.
- Record every actual invitation with `age invitation-record`, then run
  `age events-import-invitations --cohort-id EXP-ACQ-0003` after each batch.
- Record downstream outcomes only when observed (`age event-record`): acceptance, reply,
  qualified reply, meeting booked/held, proposal sent/accepted, customer won, payment received.
  No intermediate event is inferred. Absence of a reply is not evidence of absence of pain.
- An estimate is never recorded as a payment or revenue event.

## Reporting

- Every rate uses **real exposure** as its denominator: invitations actually delivered, never 51
  and never the cohort size before the invitations are sent. An `undeliverable` invitation is not
  exposure.
- Verdicts are `DESCRIPTIVE_POSITIVE`, `DESCRIPTIVE_NEGATIVE` or `DESCRIPTIVE_INCONCLUSIVE`.
  The PROCEED / ADJUST / PIVOT bands and the 51-invitation KEEP threshold are not claimed.
- Name the first materially weak transition in
  invitation → acceptance → conversation → qualified conversation → meeting → proposal → customer → payment,
  and optimise in the order revenue, customers, proposals, meetings, qualified conversations,
  replies, acceptance, sends.

## Known reporting gap (not fixed; engineering is paused)

`age marketing-engineer status` still prints the preregistered `minimum sample 51` and its KEEP
threshold, and the event log counts an `undeliverable` invitation as `invitation_sent`. Reports
for this experiment are therefore stated by hand from `age access-result` with the real
denominators above.

## Next experiment

Proposed only when (A) the frozen exposure is complete, (B) downstream evidence identifies the
largest commercial uncertainty, or (C) execution fails for a specific observable reason — and
then changing one variable, with evidence, uncertainty, control, variant, primary commercial
metric, expected learning and the result that would kill it.

## State when recorded

| | |
|---|---|
| Invitations submitted | 7 / 39 |
| Delivered (pending) | 6 |
| Undeliverable | 1 |
| Accepted / replies / meetings / proposals / customers / revenue | 0 / 0 / 0 / 0 / 0 / £0 |
| Not yet submitted | 32 |
