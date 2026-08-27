# Contact discovery — result

**Run:** 2026-08-27 · **Protocol:** `DISCOVERY-PROTOCOL.md`, fixed before any account was searched

## Answer

**No. 30 named buyers are not reachable by email.** `EXP-ACQ-0002` does not start as preregistered.

18 accounts were inspected and produced an actual observation. **Zero** had a personal mailbox for a
named commercial decision-maker published on a first-party source.

| | |
|---|---|
| Accounts observed | 18 |
| `reachable_email` | **0** |
| Wilson 95% CI | **0 - 17.6%** |
| Implied ceiling across all 55 accounts | **~10** |
| Rate required to reach 30 of 55 | **54.5%** |
| P(observing 0 in 18 if the rate were 54.5%) | **7 x 10^-7** |

The historical record agrees. `EXP-ACQ-0001` named a person at 27 accounts and found a personal
address at exactly two — Blue Frontier's `matt.kerley@` and Technical Drive's — a 7.4% rate whose
95% interval tops out at 23.4%, or 13 accounts. Two independent readings, both an order of
magnitude short of 30.

## Accounts observed

Role inbox only, no personal address on any first-party page:

```
CloudTech24        ramsac             Transputec         Littlefish
Grant McGregor     totality services  Wanstor            Nviron
Cheeky Munkey      Wavex Technology   cyberISMS          Fortitude Cyber
Secure Chain       Netitude           Zenzero            Intergence
Mitigo             NormCyber
```

Not counted: Aursec returned HTTP 403 and six guessed team-page URLs returned 404. A page that did
not load is not an observation of absence — it is a failed observation, and folding it in would
manufacture evidence for the conclusion this document reaches.

## The one candidate, and why it failed

A search summariser reported `pjob@intergence.com` as "listed in Intergence's official contact
details". It is not. The contact page carries `contact@`, `support@` and `itsupport@`; the
leadership page names six people and publishes no address at all. The claim was checked against the
site rather than accepted, and it did not survive.

This is why the protocol excludes enrichment aggregators. Every apparent hit in this run came from
RocketReach, ContactOut, LeadIQ or Growjo, and every one was either masked (`m*****@zenzero.co.uk`,
`l******@ramsac.com`), inferred from a stated format, or — for Wavex — three mutually inconsistent
addresses for the same person. An inferred address is a hypothesis about a mail server. Four of
`EXP-ACQ-0001`'s five lost sends died exactly there.

## Separate finding: a qualification defect in send 1

`EXP-ACQ-0001`'s first send is recorded to "John Hosegood, Head of Sales" at CloudTech24. He appears
in public sources as the author of a customer review of CloudTech24, not as an employee. The send
itself went to `sales@cloudtech24.com`, so the counted sample is unaffected — but the row names a
buyer who was never at the company, and it should not be reused.

## What is reachable

Named decision-makers were found for essentially every account inspected, with public LinkedIn
profiles: Netitude/Adam Harling, Zenzero/Michael Bateman, Intergence/Peter Job, Transputec/Sonny
Sehgal, Wavex/Gavin Russell, Nviron/Jamie Platt, Wanstor/Peter Lukes, Cheeky Munkey/Graham Lane,
totality services/Luis Navarro, Grant McGregor/David Lawrence.

**The constraint is the mailbox, not the person.** Names are public; addresses are not.

## What this means

Mid-market UK MSPs do not publish their commercial decision-makers' email addresses. For this ICP,
cold email is **structurally a shared-inbox channel** — and that channel has now been measured at
0/48. This is a property of the segment, not a failure of the message, and no amount of rewriting
reaches a mailbox that was never published.

## Decision

1. **`EXP-ACQ-0002` does not start.** Its preregistration stands unamended and unrun; the contract
   was not relaxed to fit the supply, which is the whole reason the protocol was written first.
2. **The email wedge against this ICP is closed** until something changes what is reachable.
3. **LinkedIn is the live candidate** — a person-specific route that demonstrably exists for this
   segment. It is a different channel with its own delivery behaviour, so it needs its own
   preregistration and its own `recipient_class`, not a substitution inside this sample.

Recorded rather than worked around. Per Rule 0.5b the idea is dormant, not dead: the revival
condition for `EXP-ACQ-0002` is a supply of 30 named-buyer addresses obtained without guessing —
from replies, referrals, event lists or inbound — not a lower bar.
