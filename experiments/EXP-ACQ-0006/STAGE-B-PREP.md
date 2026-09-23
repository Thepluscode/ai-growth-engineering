# EXP-ACQ-0006 — Stage B preparation (compliance screening packet)

**Founder decision, 2026-09-23:** the Stage A verdict is accepted as `NEGATIVE`, with ACCESS FAILED and
DEMAND NOT_ASKED. It is a finding about the Stage A access route, not evidence against demand.
**Stage B (live telephone routing, FS-001-A1 §6) is approved as the next experiment**, in two steps:

1. Produce a screened routing list and an evidence packet. **No call before the founder has seen it.**
2. Manual live routing calls, after founder or operator approval. No automated calling, and never an
   unscreened number.

The gate is `imports/marketing-engineering-os/src/theplus_growth/control_plane/outbound_contact.py`
(`FS001-OUTBOUND-1.0`). It fails closed and **does not screen**: it records what a licensed
screening source returned. The ICO's B2B live-call guidance is under review following the Data
(Use and Access) Act 2025, so every decision records the policy version it applied.

## Gate run, 2026-09-23 — the frozen cohort (30 accounts; Stage A resolved none)

| Result | Count |
|---|---|
| ALLOW | 0 |
| APPROVAL_REQUIRED | 0 |
| **DENY** | **30** |

The deny reasons, all expected from a gate that fails closed:

| Reason | Accounts | What clears it |
|---|---|---|
| TPS screening missing or UNKNOWN | 30 | licensed TPS screening, with its source and date |
| CTPS screening missing or UNKNOWN | 30 | licensed CTPS screening, with its source and date |
| Internal suppression not recorded as evidence | 30 | checked 2026-09-23: AGE `suppression` has 0 rows, so 0 matches. Record it as CLEAR with that source when the list is built |
| Prior objection not checked | 30 | Stage A produced 0 human replies, so no objection is recorded. Record it per account as `False`, with the source |
| Subscriber type unknown | 30 | per-account: corporate subscriber vs sole trader or partnership |
| Caller identity not configured | 30 | founder: the name and company given on every call |
| Callback number not configured | 30 | founder: the number displayed, and the contact or Freephone details given if asked |
| No telephone number recorded | 25 | the published corporate number from each company's own site, with the URL |
| Entity status not checked | 20 (1 more unresolved) | Companies House lookup; a dissolved or unresolved entity is a hard deny |

## Blockers that are not engineering

- **TPS and CTPS screening is licensed and paid.** The preregistration names it as FS-001's first real cash
  cost. Choosing and buying a screening service is a founder action; an agent may not enter payment
  details or create the account.
- **Caller identity and the displayed number** must be supplied by the founder.

## What happens next, in order

1. The founder chooses a screening service and supplies the caller identity and callback number.
2. Collect the published numbers (25) and the entity statuses (20 + 1), each with its source URL.
3. Screen all 30 numbers against TPS and CTPS, and record source and `checked_at`. A screening older than
   28 days is a deny.
4. Re-run the gate. Show the founder the ALLOW / APPROVAL_REQUIRED list with its evidence.
5. The founder approves. Then manual calls, recorded through the store with source and outcome.

The per-account list containing numbers stays in `imports/` (gitignored, since this repository is public).
