# Persuasion Engineering

Make genuine value easy to understand and hard to dismiss. Never manufacture pressure.

The objective is **not** to force action. Coercive tactics lift short-term conversion and charge for
it later in refunds, churn, complaints and CAC — by which point the cause is no longer attributable
to the campaign that caused it. Optimise for **maximum qualified action at minimum unnecessary
friction**, not for compliance.

Applies across the whole project: ads, SEO, email, social, landing pages, offers, sales collateral,
content, partnerships and outbound. Not outbound alone.

## The chain

```
CUSTOMER EVIDENCE → DEEP MOTIVATION → CURRENT BELIEF → DESIRED BELIEF
  → REFRAME → PROOF → STORY → OFFER → CTA → BEHAVIOUR → REVENUE + TRUST
```

Every link starts at evidence. A driver an LLM invented is a fabricated insecurity; record it in
`drivers` with an empty `evidence_id` so the gap is visible, and go and ask a customer.

## Procedure

**1. Map the drivers.** For the audience, separate emotional (fear, frustration, status, control,
belonging, identity, security, freedom, relief, achievement, loss avoidance) from logical (time
saved, money gained, cost avoided, risk reduced, probability of success, ease, speed, predictability,
ROI, opportunity cost). Each row cites a VOC quote or an observation. → `drivers` registry.

**2. Find the belief to shift.** Persuasion is usually a belief change, not a wording change.
Record current belief, the objection it produces, the new belief that must become credible, the
evidence that would make it credible, and the action that becomes logical afterwards.
→ `belief_shifts` registry.

**3. Build the reframe.** Change how the problem is interpreted, not how loudly it is stated.

> *"You may not have a lead-generation problem. You may have a lead-quality economics problem."*

**4. Generate five angles, at least one contrarian.** Common belief → counter-evidence → contrarian
claim → proof → commercial implication. State the mechanism each uses (loss aversion, contrast,
specificity, social proof, authority, identity, curiosity, risk reduction) **and what evidence it
requires to be used responsibly**. → `angles` registry.

**5. Write it.** Hook → Problem → Consequence → Reframe → Mechanism → Proof → Outcome → Offer → CTA.

**6. Tell the story.** Before → Friction → Discovery → Mechanism → Evidence → Implication → Action.
The story teaches the mechanism; it does not merely move the reader.

**7. Match the CTA to awareness.** A CTA answers: what happens, how much effort, what I get, what
risk I take, why now.

| Awareness | CTA shape |
| --- | --- |
| unaware | See the analysis |
| problem_aware | Find your leak |
| solution_aware | Compare the approach |
| product_aware | Review the diagnostic |
| ready | Start the engagement |

**8. Score 0–5** on relevance, emotional resonance, logical strength, differentiation, proof,
credibility, curiosity, specificity, offer clarity, CTA strength. **Flag every unsupported claim and
every assumption needing customer validation.**

## The gate is code, not a checklist

```python
from ai_growth_engineering.persuasion import PersuasionAsset, PersuasionIntegrityGate
PersuasionIntegrityGate.evaluate(PersuasionAsset("A-1", body, evidence_ids=("EV-1",)))
```

It refuses four things, and it is **not a score** — a strong hook cannot outvote a false claim:

- **Unsupported superlatives** — "#1", "industry-leading", "world-class", "trusted by thousands"
  without an evidence id. The rule is *cite it*, not *never say it*.
- **Scarcity without declared capacity**, and any stated limit lower than the real remaining count.
  "Only 2 left" against 48 remaining is a fabricated limit.
- **Pressure aimed at self-worth rather than value** — "your competitors are already winning",
  "serious founders don't wait". No amount of evidence licenses this; it is the line between
  persuasion and coercion.
- **A CTA that hides what happens next.**

PASS → eligible for experiment. FAIL → revise. Record the verdict in the angle's `integrity_status`.

## Authority is earned, never asserted

Do not claim to be "the only logical choice". Make the decision criteria genuinely favour us:
measured results, controlled experiments, original datasets, case studies, credentials, published
analysis, customer evidence, transparent methodology. If a claim cannot survive
`ClaimPublicationGate`, it is not authority — it is decoration.

## Measure trust, not only conversion

Every persuasion experiment carries a guardrail alongside its primary metric: unsubscribe rate,
complaint rate, refund rate, reply sentiment. A lift in qualified conversion that moves a guardrail
is not a win — it is a cost deferred to a quarter where nobody will connect it back.

Namespace: `EXP-CREATIVE-*` for angle and hook tests, `EXP-CRO-*` for page and CTA tests.

## Not permitted

Autonomous publishing. Every persuasive asset reaching a buyer goes through a human, per
`policies/growth_action_policy.json`, where `public_claim` is `require_approval` and
`unsupported_public_claim` is `deny`.
