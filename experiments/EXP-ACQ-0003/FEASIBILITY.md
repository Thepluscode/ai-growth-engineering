# LinkedIn route — feasibility, checked before anything is preregistered

**Run:** 2026-08-28 · **Status:** proposal. Nothing preregistered, nothing sent, nothing bought.

`EXP-ACQ-0002` was preregistered and *then* discovered to be unrunnable. That order is the defect.
This document is the feasibility check run first.

## Answer

**Reachable, but not free and not comparable.** Three findings, in order of how much they change
the decision.

### 1. The free tier cannot run this experiment

LinkedIn Help, verbatim:

> "Basic and free LinkedIn members can include a personalized message to five connection requests
> per month. LinkedIn Premium members can send unlimited personalized messages with their
> connection requests."

Five per month. A 30-send minimum takes **six months** on a free account — longer than the thing
it is testing is worth. The wedge depends on a per-account observation from a teardown, so a blank
connection request is not a cheaper version of the message; it is a different message with no
content.

This is first-party. The widely-quoted figures for weekly invite caps and note character limits
come from automation vendors — Cleverly, PhantomBuster, Evaboot, Taplio — selling tools to exceed
them. That is the same class of source whose email addresses did not survive verification in
`EXP-ACQ-0002`, so their numbers are recorded here as unverified and not relied on. LinkedIn
states plainly that it does not publish the thresholds: *"LinkedIn Support cannot disclose the type
or reason for the restriction."*

### 2. The cost, from LinkedIn's own pricing page

| Plan | Price | InMail |
|---|---|---|
| Sales Navigator Core | **US$119.99/month** or US$1,079.88/year | 50/month |
| Sales Navigator Advanced | US$159.99/month or US$1,799.88/year | 50/month |

Source: `business.linkedin.com/sales-solutions/compare-plans`, read 2026-08-28. GBP figures are
shown on that page but were not captured; a widely-quoted £94.99 for Core is **unverified**.

Sales Navigator is not obviously the right purchase. The binding constraint above is *personalised
connection notes*, which LinkedIn says any **Premium** account unlocks — and Premium is cheaper
than Sales Navigator. Sales Navigator buys search filters and 50 InMails, neither of which the
experiment needs when the account list already exists in `sales/teardowns/`. **Price Premium
before buying Sales Navigator.**

### 3. The metric is not comparable to `EXP-ACQ-0001`

Email had one step: it arrived or it bounced. LinkedIn has three.

```
email      send ----------------------------------> reply
linkedin   invite --> accept --> message --> reply
```

A connection request is **not a delivery**. An unaccepted invite is never read, and it is not a
bounce either — it is a silent non-event with no signal at all. So:

- "Meaningful reply rate per send" means something different on this channel, and reusing
  `EXP-ACQ-0001`'s 10% / 5% thresholds against it would compare two different quantities. The
  thresholds were held constant for `EXP-ACQ-0002` precisely because that route *was* comparable.
  This one is not.
- The honest primary metric is a funnel: **invite → accept rate**, then **accept → reply rate**.
  The first is the new unknown and has no baseline here at all.
- The note is character-limited, so the OBSERVATION + ECONOMIC HYPOTHESIS + LOW-FRICTION CTA
  message cannot be sent as written. **The channel change forces a message change**, which means a
  null result cannot be attributed to either one. That confound has to be designed around before
  this is worth running, not explained afterwards.

## Supply — partially checked

Named commercial decision-makers with public LinkedIn profiles were found for **10 of 10** accounts
looked at during `EXP-ACQ-0002`'s discovery: Netitude/Adam Harling, Zenzero/Michael Bateman,
Intergence/Peter Job, Transputec/Sonny Sehgal, Wavex/Gavin Russell, Nviron/Jamie Platt,
Wanstor/Peter Lukes, Cheeky Munkey/Graham Lane, totality services/Luis Navarro,
Grant McGregor/David Lawrence.

10 of 10 is encouraging and is **not** 30 verified. Verifying 30 is the next step, and it is
deliberately not taken yet: the spend decision below gates it, and researching 30 profiles for an
experiment that may not be funded is the kind of activity that looks like progress.

## The engine is ready for it

`outreach.channel` landed 2026-08-28 and is mutation-verified. A LinkedIn send cannot be counted in
the email numbers:

```
$ age recipient-split --db .age/growth.db
                       route   sent  replies  rate
           email/named_buyer      2        0  0.0%
            email/role_inbox     48        0  0.0%
```

`linkedin/named_buyer` would appear as its own route, never merged into the rows above.

## What is being proposed, and what is not

**Proposed — a decision for a person, not for the system:**

1. Buy the cheapest LinkedIn tier that unlocks unlimited personalised connection notes. Verify it
   is Premium and not Sales Navigator before paying the difference.
2. Accept that this experiment measures a **funnel**, not a send-to-reply rate, and that its
   thresholds must be set from the invite-accept step rather than inherited.

**Not done, deliberately:** nothing is preregistered, no profiles beyond the ten are researched, no
subscription is bought and no invitation is sent. Buying a subscription is money and sending
invitations is external contact; both are proposed and stopped, per the standing rule.

If the spend is declined, the finding is complete and worth recording as it stands: **for this ICP,
both reachable routes are paid.** Email reaches only shared inboxes, and the personal route costs a
monthly subscription. That is a real property of selling into mid-market UK MSPs, and it belongs in
the pricing and channel model rather than being rediscovered a third time.
