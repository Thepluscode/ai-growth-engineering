# EXP-ACQ-0002 — the named-buyer route

**Preregistered:** 2026-08-27 · **Status:** contract frozen, zero sends executed

## Why this exists

`EXP-ACQ-0001` returned `REVIEW` on 0/50. 48 of those sends went to a shared inbox and 2 to a
named buyer. The route the wedge was written for was never tested: at n=2, a true 10% rate
returns zero replies **81%** of the time.

This experiment tests that route, and nothing else. It is not a second attempt at the same
question — the population is different by construction.

## Hypothesis

The same pipeline-leak message, delivered to a **named commercial decision-maker's own mailbox**
at a qualified UK MSP, produces a meaningful reply rate of >=10%.

## Contract

| | |
|---|---|
| Primary metric | `meaningful_reply_rate` |
| KEEP | >= 10% |
| ITERATE | 5 - 9.9% |
| REVIEW | < 5% |
| Minimum sample | **30 delivered sends, all `recipient_class = named_buyer`** |

Thresholds are unchanged from `EXP-ACQ-0001` on purpose: a moved goalpost would make the two
routes incomparable, which is the one thing this experiment exists to compare.

## What n=30 can and cannot decide

| | |
|---|---|
| P(0 replies given a true 10% rate) | **4.2%** — 0/30 rules out KEEP |
| P(0 replies given a true 5% rate) | **21.5%** — 0/30 does **not** rule out ITERATE |

Stated up front so nobody reads a null result as more than it is. 30 was chosen as the smallest
sample that can reject the KEEP threshold; rejecting 5% as well would need roughly 60.

## Admission rule — the defect this contract closes

A send counts toward the minimum sample only if **all** of these hold:

1. `stage != 'bounced'` — it arrived.
2. `recipient_class = 'named_buyer'` — a specific person's own mailbox, evidenced in `notes` by
   the address itself.
3. The address was **discovered before the message was written**, not substituted afterwards.

`info@`, `contact@`, `enquiries@`, `sales@`, `hello@`, `support@`, `cyber@`, `uksales@` and a
subject line that asks to be forwarded to someone are **`role_inbox`**. A request to route is not
a delivery to a buyer. `EXP-ACQ-0001` treated "the message left the outbox" as a qualified send,
and the wording held while the intent failed.

Contact discovery is therefore a **gate, not a step**: an account with no reachable named buyer is
excluded from the sample rather than downgraded to its shared inbox. Excluding it costs one
account. Including it cost the last experiment its conclusion.

Enforced in code as of 2026-08-27:

```
$ age recipient-split --db .age/growth.db
 recipient_class   sent  replies  rate
     named_buyer      2        0  0.0%
      role_inbox     48        0  0.0%
    unclassified      0        0  n/a
```

`recipient_class` is a required, validated column on every imported send. An unrecognised value
raises rather than defaulting, and a row that predates the column reports as `unclassified` rather
than being absorbed into either route.

## Prior

`role_inbox` is at 0/48. That is not this experiment's control — the two populations differ in
more than the mailbox — but it is the number this route has to beat to be worth a third attempt.

## What this does not authorise

No sends. No product feature. The freeze in `FEATURE_TRACKER.md` holds. The next move is contact
discovery against the accounts already researched in `sales/teardowns/`, which is internal work;
the sends themselves are external surface and are proposed, not executed unattended.
