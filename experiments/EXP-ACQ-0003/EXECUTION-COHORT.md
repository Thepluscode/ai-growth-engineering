# EXP-ACQ-0003 — execution cohort, frozen

**Frozen:** 2026-09-08 · **Cohort:** 39 accounts · **Status:** ready to send, **zero invitations sent**

## The cohort

| | |
|---|---|
| QUALIFIED accounts holding an admissible LinkedIn identity | **39** |
| — two-source identity (register **and** profile) | 28 |
| — single-source identity (profile only) | 11 |
| Ownership: MULTI_DIRECTOR / SINGLE_DIRECTOR / UNKNOWN | 26 / 5 / 8 |
| Identities excluded for inadmissible upstream lineage | **7** |

The 7 exclusions are identities sitting on rows that were never qualified. They were
being counted as supply until the scoreboard fix exposed the same defect one stage up.
Sourcing is frozen; the remaining Companies House pool is untouched.

## The invariant, now enforced in code

```
NO DOWNSTREAM STATE WITHOUT ADMISSIBLE UPSTREAM LINEAGE

candidate   is not  qualified
identity    is not  access
acceptance  is not  demand
reply       is not  pain
pain        is not  willingness to pay
proposal    is not  revenue
```

Each stage is a separate table and a separate assertion:

- `freeze_execution_cohort` admits only prospects with an explicit `qualified%` status
  **and** a LinkedIn identity. Mutation-checked: relaxing the predicate back to
  `NOT LIKE 'disqualified%'` is `KILLED` from a green baseline, file restored byte-identical.
- `record_invitation` refuses any prospect outside the frozen cohort.
- `access_result` reads only the `invitations` table. **A test asserts that 39 accepted
  connections move `meaningful_responses`, `discovery_calls`, `diagnostics_proposed`,
  `commercial_proposals`, `paying_customers`, `collected_revenue_pence` and `outreach_sent`
  by exactly zero.**
- The cohort cannot be refrozen, and the treatment is frozen: recording an invitation that
  carried a note raises `treatment_changed`.

## Decision bands, as counts

| Accepted of 39 | Verdict |
|---|---|
| 0–7 | **PIVOT** — the invitation mechanism itself is weak; do not expand sourcing to compensate |
| 8–28 | **ADJUST** — route viable, short of the downstream sample; compute expansion from the *observed* rate |
| 29–39 | **PROCEED** — enough access to expose the unchanged message |

29 is the accepted-connection count the message stage needs to reject KEEP at a true 10%
reply rate. Asserted at every boundary (0, 7, 8, 28, 29, 39).

**The verdict is `NOT_EVALUABLE` until all 39 have settled.** A partial cohort returns no
verdict at all — reading one early is how an experiment gets stopped on noise.

On ADJUST the expansion is computed, not guessed:
`ceil((29 − accepted) / observed_accept_rate)` additional verified identities, then
backwards through the measured sourcing funnel. At 12 accepts that is 56, not 100.

## Denominators

The accept rate divides by **invitations submitted**, never by cohort size: an invitation
that was never sent is not a refusal. With nothing submitted the rate is `None`, never 0.0.

## Why the invitations are not sent yet

**This is an operator action, not an agent action, and I have stopped at the boundary.**

Sending requires being signed into a LinkedIn account. I have no LinkedIn access, and the
preregistration forbids using the founder's authenticated session or automating around
platform limits — restricting the account this experiment depends on would cost more than
the data. Each invitation is also external contact with a named person, which is proposed
and stopped, never executed unattended.

What is ready: `.age/exp-acq-0003-send-sheet.md` — 39 rows, profile URL, identity strength,
ownership, and the exact command to record each outcome. It is deliberately **not
committed**: this repository is public and those rows are personal data.

```bash
age cohort                                    # the frozen 39
age invitation-record --prospect-id 7 --outcome accepted --accepted-at 2026-09-10T10:00:00Z
age invitation-record --prospect-id 8 --outcome pending
age access-result                             # verdict once all 39 have settled
```

## What happens after PROCEED

The **unchanged** `EXP-ACQ-0001` message goes to accepted connections only. Not shortened,
not personalised, not A/B tested, not rewritten. Changing it mid-experiment reintroduces the
channel/message confound the note-less design was built to remove.

## Not done

No invitation sent. No message written. No subscription bought. No sourcing extended. No
email inferred. The 10 BORDERLINE and 20 REJECTED candidates remain unseeded.
