# Demand cycle 2026-10: protocol

Founder scope amendment to `weekly_marketing_cycle_v1`, dated 2026-10-06. It doesn't replace the
experiment machinery or start a new project. It makes the existing acquisition experiments able
to measure **demand** instead of just counting sends.

## Markets and variants

| Market | Variant A: discovery (`named-buyer-discovery-v1`) | Variant B: outcome offer (`named-buyer-message-v1`) |
|---|---|---|
| `MKT-PAYMENT-RELIABILITY` | EXP-ACQ-0011 | EXP-ACQ-0009 (history kept: 13 sends to date) |
| `MKT-EU-AI-GOVERNANCE` | EXP-ACQ-0012 | EXP-ACQ-0008 |
| `MKT-SECURITY-INVESTIGATION` | EXP-ACQ-0013 | none this cycle: CyberGuardPlus isn't pitched until pain is confirmed |
| `MKT-GROWTH-TEARDOWN` | parked, not deleted: still a valid hypothesis, but it doesn't test CyberGuardPlus demand | EXP-ACQ-0010 history kept |

The two variants are separate protocols, so `markets.compare` and `age funnel` never pool them.
Within a market, prospects are assigned to arms alternately in research order, which keeps
buyer quality and routing comparable. **A winner isn't inferred below 30 named-buyer
deliveries per arm**, and even at 30 a single-digit difference is noise.

Credit a draft to a variant explicitly:
`age marketer import <MARKET> --experiment-id <EXP> --file <private json>`. If a market runs two
variants and none is chosen, the import is refused.

### Variant A: discovery (no pitch)

> {one factual sentence from the evidence trigger}
>
> I'm trying to understand how teams like yours handle {workflow} when it goes wrong, not selling anything.
>
> When did this last happen, and what did your team actually do to resolve it?

### Variant B: outcome offer

> {one factual sentence from the evidence trigger}
>
> {one-sentence hypothesis about the business consequence}
>
> We run a fixed-scope {diagnostic}. Would a one-page outline of what it covers be useful?

### Payment market copy (founder direction, 2026-10-06)

Positioning: *TrustLedger helps payment teams explain and resolve the transactions their
systems can't agree on.* The central reframe is that payment exceptions are an evidence
problem, not a matching problem: **the expensive part of reconciliation isn't matching
payments, it's investigating the ones that refuse to match.** The software is how the work gets
done. The buyer is paying for avoided loss, recovered analyst time and certainty.

- **A (EXP-ACQ-0011):** after the evidence sentence: "When a payment or settlement record doesn't reconcile cleanly, how does your team work out what actually happened? … the ugly cases (duplicates, unknown states, fee mismatches, missing provider events) … I'm researching the workflow rather than pitching software." CTA: "Would you mind telling me about the last one that was genuinely painful?"
- **B (EXP-ACQ-0009):** after the evidence sentence: the reframe, the workflow that sits behind it, then "a narrow, fixed-price service that takes one recurring exception type and maps where it originates, how much analyst time it consumes, what evidence is missing, and which part can safely be eliminated or automated. I'm not assuming you have this problem." CTA: "Would you be open to telling me how your team handled the last payment exception that took longer than it should have?"

Both arms ask about the last real exception. **The only variable is whether the bounded offer
is described.** Not allowed in the copy: invented scarcity, social proof, "leading platform",
"AI-powered". Until a customer exists, proof means technical proof of work only, labelled as
such.

**Diagnostic scope (the £1,500 offer), once a buyer engages.** One workflow, one exception
class, fixed price, fixed deliverable, no platform migration. Deliverables:

- current workflow map;
- exception taxonomy;
- root cause;
- measured analyst effort;
- evidence and control gaps;
- automation opportunities, and what stays human-controlled;
- a prioritised plan;
- an ROI estimate.

**Follow-up after a pain reply.** Don't pitch yet. Ask how often it happens, how long a normal
one takes, and who gets pulled into the hard ones. Then do the arithmetic with the buyer's own
numbers (exceptions × minutes × loaded hourly cost) before offering to map one exception class.

## Routing gate: qualified isn't send-ready (amended 2026-10-06)

**Qualified** means the company fits, a named buyer exists and there's an evidence trigger
(name and quote verified on fetched pages by `marketer.verify`). **Send-ready** also needs a
verified direct route. The workbench derives each draft's route state; nobody types it in:

| Route state | Meaning | What's allowed |
|---|---|---|
| `ROUTE_UNVERIFIED` | a name to find on LinkedIn later | nothing. Shown as blocked on the send sheet; a send is refused |
| `PROFILE_VERIFIED` | a profile link published on a fetched page | Stage A only: a connection request with a short note. No InMail |
| `DIRECT_VERIFIED` | a published personal email, or an accepted 1st-degree connection with Message available | Stage B: the experiment message |

The funnel is staged so you can see where a failure happens:

```
QUALIFIED → PROFILE_VERIFIED → CONNECTION_REQUEST_SENT → CONNECTION_ACCEPTED → DIRECT_VERIFIED
  → DISCOVERY/OFFER_MESSAGE_SENT (delivery unverified) → DELIVERY_VERIFIED → MEANINGFUL_REPLY
  → discovery → pain → spend → paid
```

`PROFILE_VERIFIED` hasn't passed the route gate. It means a legitimate connection request can be
attempted. Only `DIRECT_VERIFIED` enters the message send path. Connection acquisition (requests
sent, accepted, pending, direct routes created) is reported apart from demand. LinkedIn doesn't
report declines, so a request stays pending until it's accepted.

- A connection request (`age draft connect`) is access only. It's never a send or a delivery, and it isn't the experiment's message.
- The experiment's message is never shortened to fit a 300-character note. **The demand experiment starts when the real message goes out through a verified direct route.**
- **Delivered needs evidence that's separate from the send.** That means a `message_delivered` event recorded with `age draft delivered <id> --evidence linkedin_seen_indicator` once LinkedIn shows the message as Seen, or a reply, which proves delivery after the fact. A send never creates its own delivery, even to an accepted connection; a regression test enforces this. Until then the message counts as `attempted, delivery unverified` and stays out of every denominator.
- The 13 EXP-ACQ-0009 sends of 2026-09-30 are kept as attempts and now read as unverified.
- Shared inboxes (`info@`, `support@`, contact forms) are refused for market experiments (`named_buyer_required`).

Route acquisition is tracked per qualified prospect in the private evidence set, with these fields: `route_searched`, `route_found`, `route_type`, `route_verified`, `route_unavailable_reason`. No email is ever guessed, and the named-buyer standard isn't lowered to gain volume. While route coverage is poor, **improve routes on the qualified set before researching more companies.**

### Distribution constraint (evidence, 2026-10-06)

Dedicated route searches covered 22 qualified buyers. Only 5 have a published public profile
link, and **none has a published direct route**. For the other 17 there's nothing usable: no
profile link, and no personal email published verbatim. Their pages link to company LinkedIn
pages only, and the NCSC listings obfuscate their emails. This is a **distribution and access
constraint**. It isn't evidence of no pain, no demand, or a failed thesis, and it isn't solved
by guessing contact details or loosening the route definition.

Legitimate next access mechanisms:

- connection requests to verified profiles (running);
- warm introductions;
- relevant industry events;
- professional communities;
- associations or directories where contact details are intentionally published;
- people the founder knows who can introduce.

Searching harder on public pages is unlikely to raise coverage much.

### Queue decisions (2026-10-06)

| Drafts | Decision | Reason |
|---|---|---|
| 12 EXP-ACQ-0009 offer drafts from 2026-09-30 | rejected and kept | `SUPERSEDED_COPY_AND_MISSING_EVIDENCE_TRIGGER` |
| 15 EXP-ACQ-0008 offer drafts from 2026-09-30 | held and kept | they predate the evidence-trigger rule. They come back only with a named buyer, evidence trigger, valid route, current market, explicit variant and current thesis |
| 15 EXP-ACQ-0010 drafts | held and kept | `MARKET_PARKED` |

Held drafts can't be approved or sent.

### Route evidence correction (2026-10-20)

The workbench read every `https://` identity as `PROFILE_VERIFIED`, so a profile link needed no
fetched page while an email did (fixed for emails on 2026-10-13). Profiles now follow the same
rule: `PROFILE_VERIFIED` needs evidence written by fetching a page that publishes the exact link,
and an accepted connection on an unevidenced profile is not `DIRECT_VERIFIED`. `age draft
verify-route <id> --url <page>` attaches evidence to an existing draft; it fetches the page itself.

Effect on the live queue (20 open profile-link drafts before the fix):

| Drafts | Result |
|---|---|
| #70, #71, #83, #84 | verified against the route page recorded in the evidence set → `PROFILE_VERIFIED` |
| #87, #88 | connection requests already sent; no recorded page publishes the link → `ROUTE_UNVERIFIED` |
| #90–#103 (14) | created together on 2026-10-13 with no marketer run and no route source; #90 and #95 refused against the pages on file → `ROUTE_UNVERIFIED` |

No row was deleted and no event changed: the route fields of #70, #71, #83 and #84 were written,
and every other draft's route state moved only in derivation. Each unresolved draft becomes a
route again only when a page that publishes its link is named and fetched.

Codex review (2026-10-20) found the "exact link" test was substring containment, so a page
carrying only a longer profile link vouched for a shorter one. It now requires the whole link
(regression test in `tests/test_route_gate.py`); the four verified drafts still pass. Two limits
stand: `verify-route` writes its evidence fields without an event or a page snapshot, so the
digest is not independently re-checkable; and a marketer candidate that `verify()` accepted can
still be refused when `_store` refetches the page, because the second fetch can differ.

**Sample size caveat for the 30-delivery gate.** At 30 verified deliveries per arm, a two-sided
5% test with 80% power detects a reply-rate gap only from 10% to about 41%. Telling 10% from 15%
needs about 686 per arm. `COMPARISON_ALLOWED` is an operational review threshold, not a powered
test, and a difference read there is directional unless it is that large.

## Progressive evidence gates (verified named-buyer deliveries per arm)

| Deliveries | Gate | What may be concluded |
|---|---|---|
| 5 | `ROUTE_MECHANICS_REVIEW` | is the message reaching the intended buyer? |
| 10 | `CATASTROPHIC_MISMATCH_CHECK` | is there a gross message/ICP mismatch? Never a winner |
| 15–20 | `DIRECTIONAL_ENGAGEMENT_AND_PAIN` | direction of engagement and pain evidence |
| 30+ comparable per arm | `COMPARISON_ALLOWED` | formal discovery-versus-offer reply-rate comparison |

Below 30 the evidence is qualitative. With five payment prospects split across five unrelated
companies, the company's characteristics would dominate any difference between arms. Don't push
mechanically on to 30 if earlier evidence shows a thesis or an acquisition mechanism is
fundamentally invalid. Classify the reason accurately instead.

## Payment sub-hypothesis: the residual exception

> Existing reconciliation platforms may solve routine matching while leaving a costly residual
> workflow in which analysts manually investigate unmatched or disputed exceptions across
> multiple systems.

Observation: all five payment prospects researched on 2026-10-06 already use AutoRek or Aurum.
That's evidence the market is mature. **It isn't yet evidence that the residual workflow is
painful.** TrustLedger isn't repositioned around this until buyers confirm it. When a payment
buyer engages, ask:

1. What happens to the items your reconciliation system can't automatically match?
2. Who investigates them?
3. How are they prioritised?
4. How many stay unresolved on a normal day or week?
5. How long does a difficult exception take?
6. Which other systems does the analyst have to check?
7. Can the recurring causes be identified?
8. How is the resolution documented?
9. Could another analyst later reconstruct why the decision was made?
10. What proportion could safely be automated?
11. What stops your current reconciliation platform from solving that part?

Question 11 decides whether there's a wedge, or whether incumbent configuration already covers it.

## Discovery questions (once a buyer engages)

Ask about what happened, not what they think:

- Tell me about the last time this happened.
- What triggered it? How did you detect it? What did you do next?
- Which systems or tools were involved? Who else got involved?
- How long did resolution take? Which parts were manual?
- What happens if it isn't resolved correctly or quickly?
- How often does it happen?
- What do you currently pay for the software, services or people involved?
- Where do those tools still fail?
- Who owns the budget for fixing this workflow?

Never ask: "Would you buy this?", "Would AI help?", "Would you pay £X?", "Do you like this idea?"

Record what the buyer says with `buyer_truth.record_commercial_evidence` against the reply or
meeting event, using `experiment_id` = the variant's experiment:
`PAIN_CONFIRMED` (pain), `BUDGET_SIGNAL` (existing spend; there's no narrower category, and the
funnel names the mapping), `PROPOSAL_REQUESTED` (solution request), `ALTERNATIVE_MENTIONED`
(current tools).

## Funnel and denominator

`age funnel --evidence-set private/<file>.json` reports fifteen stages per market and per
variant. The primary rate is **meaningful replies / delivered to named buyers**, shown only at
or above 30. Historical attempts are never the denominator.

## Thesis states (exit criteria)

Derived, strongest evidence first: `PAID_COMMITMENT` > `PAID_TEST_REQUESTED` > `SPEND_CONFIRMED`
> `PAIN_CONFIRMED` > `PAIN_NOT_CONFIRMED` (only after 5+ discovery conversations with no pain) >
`ACCESS_INCONCLUSIVE`.

- Replies alone never raise a thesis above `ACCESS_INCONCLUSIVE`.
- A routing failure never lowers one to `PAIN_NOT_CONFIRMED`.
- `STOP_THESIS` is a founder decision, recorded as the market's status. It's never computed. Under Rule 0.5d it stops a thesis, never the project.

## Historical evidence: how to read the zeros

As of 2026-10-06 the store holds 84 outreach sends, 0 meaningful responses, 0 discovery calls
and £0 revenue. They stay on record. Current interpretation: **an acquisition/access failure,
not yet sufficient evidence that demand is absent.**

- **Weak or shared routing.** EXP-ACQ-0001 sent 50 messages, of which 48 went to role inboxes (`info@`, `contact@`) and 2 reached a named buyer (`experiments/EXP-ACQ-0001/VERDICT.md`).
- **Failures before reaching a buyer.** EXP-ACQ-0006's Stage A failed its access and routing gates, and demand was never asked. EXP-ACQ-0003 had 4 of its 34 LinkedIn invitations undeliverable and 1 accepted.
- **The underlying pain was never tested.** Every prior message pitched an offer. None asked a buyer about a recent instance of the workflow, so no message could have produced a pain confirmation.
- **The only clean named-buyer sample is small.** EXP-ACQ-0009 sent 13 messages by hand on LinkedIn (2026-09-30), against a minimum of 30. P(0 replies | n=13, true rate 10%) ≈ 25%. It isn't recorded whether these were connection notes awaiting acceptance or messages. Since 2026-10-06 they read as `attempted, delivery unverified` and sit outside every denominator.

## Doctrine interpretation for this cycle

Rules 0.10 and 0.5d stand unchanged. Read narrowly here: having no buyer evidence doesn't
require an engineering shutdown, but it doesn't justify speculative features either. Build work
must improve validation, delivery reliability, an observed customer requirement, or an existing
operational or security obligation. If a buyer names a capability that blocks a paid test, it's
recorded as buyer evidence and goes through the existing build doctrine.
