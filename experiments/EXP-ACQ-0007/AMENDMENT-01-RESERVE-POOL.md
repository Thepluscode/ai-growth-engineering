# EXP-ACQ-0007 — Amendment 01: reserve pool and replacement rule

**Amended:** 2026-09-16T15:27:44+00:00 · **Pre-treatment.** `OUTREACH_SENT = 0`,
messages generated = 0 at the time of this amendment, outcomes observed = 0.

| | |
|---|---|
| Amends | `PREREGISTRATION.md` at `sha256 c726c73632be18ccc96ba8571dc0f97a312c2d09be58365872bf687bf6e507b7` |
| Reason | denominator resilience — 30 assigned per arm against a 30-matured-exposure floor left no tolerance for pre-treatment invalidation |
| Replacement rule version | `replacement-rule.v1` |
| Reserve register | `reserve.csv`, 13 accounts |

`PREREGISTRATION.md` is **not** edited. It stands byte-identical at the hash above; this file is
the amendment record and is itself hashed and cited in the tracker.

## What does not change

The cohort, the assignment and the metric are untouched. No account is added to the 60, no account
is moved between arms, and nothing is rerandomised. ITbuilder `04296864` remains excluded for the
reason recorded in the preregistration.

**The statistical limitation stands exactly as written.** A non-significant result at 30/30 is
`INSUFFICIENT_SAMPLE`. It is never evidence of `NO_DIFFERENCE` and never a claim that the two
procedures perform alike. This amendment buys tolerance against invalid accounts; it does not buy
power, and the experiment was deliberately not enlarged to manufacture significance.

## The reserve pool

13 accounts, each independently satisfying the same frozen qualification rule as the 60: UK active
legal entity · live first-party site · clear MSP / cyber / IT-services offer · repeatable B2B
motion · named current decision-maker on the register · at least 4 commercial-complexity signals.
BORDERLINE does not count.

| Check | Result |
|---|---|
| Reserve count | 13 (≥12 required) |
| Unique company numbers / domains | 13 / 13 |
| Overlap with the 60 (number and domain) | none |
| Overlap with the prior-contact exclusion list | none |
| Every entity active with a named current officer | yes |
| Every entity ≥4 complexity signals | yes |
| BORDERLINE or unresolved-fetch accounts included | none |

A reserve is **not an experimental observation** and enters no denominator unless activated by the
rule below. `reserve.csv` carries register identity and an officer count only; officer names stay
in the local working file, as for the cohort.

Sourcing was read-only: Companies House public register plus each company's own site. No contact
enrichment ran and no credit was consumed. Rejected during verification: accounts under 4 signals,
one domain now serving a gambling affiliate site, one company absorbed by an acquirer, and several
whose site could not be tied to an active entity — those are recorded UNRESOLVED, never as
rejections of the market.

## Replacement ordering — frozen, not discretionary

```
reserve rank = sha256("EXP-ACQ-0007/reserve|" + company_number)
ordered ascending; the lowest unused rank replaces the first invalidated account
```

The digest is published per row in `reserve.csv` as `reserve_key`, so the order recomputes from the
rule alone and no reserve can be chosen for convenience at the moment it is needed.

| Rank | Account | Number |
|---|---|---|
| 1 | Andromeda Solutions | `08628185` |
| 2 | Advantage Business Systems | `01778540` |
| 3 | Aptus Technology | `04425747` |
| 4 | Absolute Networks | `04851663` |
| 5 | A.S.E. Computer Services | `04645219` |
| 6 | Bespoke IT Solutions | `08992273` |
| 7 | Ask4Support | `07767536` |
| 8 | Custom Computer Services (Wales) | `03366720` |
| 9 | Adept Communications and Technology | `04901558` |
| 10 | Auxilium IT Consultancy | `SC618188` |
| 11 | Complus IT | `09667114` |
| 12 | Belper Technology | `13567165` |
| 13 | 4Cambridge | `10473812` |

**A replacement inherits the arm of the account it replaces.** If a `baseline` account is
invalidated, the next unused reserve joins `baseline`; likewise for `candidate`. There is no
rerandomisation, and an activated reserve is recorded with the date, the invalidated account and
the objective reason.

## When a reserve may be activated

Only for an objective eligibility failure discovered **before meaningful treatment exposure**:

- the legal entity is no longer active on the register
- the company identity is proven wrong (the site does not belong to the assigned entity)
- prior-contact overlap is discovered
- the decision-maker is no longer current and no current eligible decision-maker can be established
- the first-party site or offer no longer satisfies the frozen qualification rule
- hard delivery failure before exposure

On that last one, AGE's own policy already agrees and no policy was changed to make it fit:
`DELIVERED = {"message_sent", "invitation_sent"}` while `ATTEMPTS` additionally contains
`message_bounced` (`segments.py`). A hard bounce is an attempt that never becomes a delivered
exposure, so it never enters the denominator and replacing it removes no observation.

## When a reserve may NOT be activated

- no reply
- a negative reply
- weak engagement
- a low score after valid exposure
- treatment underperformance
- an inconvenient experimental outcome

The line is the distinction the whole amendment exists to hold: a reserve may repair an account
that was never validly exposed, and may never repair a result. Any replacement outside the list
above is a protocol violation and is reported as one rather than absorbed.

## Authority

Unchanged. No sending, no invitations, no email, no sequence activation, no publication, no
credit-consuming enrichment.
