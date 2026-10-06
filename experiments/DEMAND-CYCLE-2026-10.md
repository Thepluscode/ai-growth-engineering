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

## Routing gate: what counts as a demand-test attempt

A prospect counts toward the named-buyer demand denominator only when **all** of these hold:

1. a named buyer is identified and the name appears on a fetched public page (enforced by `marketer.verify`);
2. their role is relevant to the hypothesised pain (the `ownership_reason` in the evidence set);
3. there's a concrete evidence trigger, quoted verbatim from a fetched page (enforced);
4. there's a plausible direct route: a verified email (`high`), a verified profile link (`medium`), or a name-only LinkedIn lookup (`low`, counted as researched but not as a valid direct route);
5. the delivery can be recorded (workbench send, then a bounce if one arrives).

`info@`, `support@`, contact forms and role inboxes are refused for market experiments by the
workbench (`named_buyer_required`). They can be tracked under an unlinked draft, but they never
enter the denominator.

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
- **The only clean named-buyer sample is small.** EXP-ACQ-0009 sent 13 messages by hand on LinkedIn (2026-09-30), against a minimum of 30. P(0 replies | n=13, true rate 10%) ≈ 25%. It also isn't recorded whether these were connection notes awaiting acceptance or messages, so their delivery is operator-asserted.

## Doctrine interpretation for this cycle

Rules 0.10 and 0.5d stand unchanged. Read narrowly here: having no buyer evidence doesn't
require an engineering shutdown, but it doesn't justify speculative features either. Build work
must improve validation, delivery reliability, an observed customer requirement, or an existing
operational or security obligation. If a buyer names a capability that blocks a paid test, it's
recorded as buyer evidence and goes through the existing build doctrine.
