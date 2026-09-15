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

## Verification rules (founder, 2026-09-16)

- Examples are never observations. An outcome is recorded only after LinkedIn read-only
  verification or an explicitly identified real-world event.
- An acceptance is recorded only when LinkedIn shows it (the person has left the Sent invitations
  list and ordinary messaging is available). The frozen follow-up is sent only then.
- Sales Navigator InMail is never used. If it is the only messaging path, nothing is sent.

## Exposure accounting

| Exposure | Treatment |
|---|---|
| Six invitations recorded 2026-09-15 | delivered, counted |
| One invitation recorded 2026-09-15 as `undeliverable` | attempted submission; **not** exposure |
| Acora (one frozen buyer), invited about 6 days before 2026-09-16 | **pre-batch, protocol-conforming exposure**: sent after the freeze, standard invitation, no note, verified pending on LinkedIn. Counted in the primary denominator. Send date **estimated** as 2026-09-10 from LinkedIn's relative-time display; sender unknown |

**Primary descriptive denominator:** delivered exposures including the pre-batch exposure.
**Sensitivity check only:** the same rate excluding it. Never the headline.

## Next experiment

Proposed only when (A) the frozen exposure is complete, (B) downstream evidence identifies the
largest commercial uncertainty, or (C) execution fails for a specific observable reason — and
then changing one variable, with evidence, uncertainty, control, variant, primary commercial
metric, expected learning and the result that would kill it.

## State when recorded

| | 2026-09-15 | 2026-09-16 (LinkedIn-verified) |
|---|---|---|
| Invitations submitted | 7 / 39 | 8 / 39 |
| Delivered (pending) | 6 | 7, including the Acora pre-batch exposure |
| Undeliverable | 1 | 1 |
| Accepted / replies / meetings / proposals / customers | 0 / 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 / 0 |
| Revenue | none observed | none observed |
| Not yet submitted | 32 | 31 |
| Acceptance rate | 0 / 6 | **0 / 7** (sensitivity: 0 / 6 excluding Acora) |
