# Digital Marketing Roadmap — Evidence Before Automation

This roadmap covers the Digital Marketing Project. AI Growth Engineering supplies the evidence,
experimentation and controlled-automation layer. Capability families are activated by market or
customer evidence, not by the current UK Cyber/MSP experiment alone.

## V0 — Market Experiment 001 + Revenue Evidence OS (NOW)

Build only what increases learning or closes the first customer:

- prospect registry
- evidence registry
- Growth Leak Teardowns
- outreach quality gate
- suppression registry
- experiment preregistration
- revenue scoreboard
- action-policy skeleton

**Promotion gate:** at least 1 paying customer and real delivery evidence.

## V1 — Delivery Instrumentation

Only after a paying Sprint exposes the need:

- client funnel baselines
- offer/congruence scoring
- query-to-revenue lineage
- experiment evidence reports
- contribution-profit calculations
- decision log

**Promotion gate:** >=3 paying clients and at least one repeated delivery workflow.

## V2 — Internal Growth Operator

Automate repeated internal work, not client-facing autonomy:

- market-research skill
- customer-intelligence skill
- competitor pattern extraction
- experiment-surface generation
- creative-family registry
- anomaly detection
- recommended next action

All writes remain behind explicit approval/policy.

## V0.3 — Product Opportunity Portfolio

Implemented as an evidence and decision layer, not a product factory:

- hard product build gate
- opportunity and product-format registries
- scoring only after eligibility
- smallest-justified-format decision
- Opportunity Graveyard with reopen conditions
- validate at most the top three eligible candidates

Current result: five existing offers were analysed and all remain in research. No candidate passes
the product build gate, so there is no ranked top three and no new product build.

## V3 — Growth Control Plane Candidate

Only if repeated customer workflows justify productisation:

- identity / tenant boundaries
- delegated authority
- claims policy
- budget policy
- action risk classes
- approval workflows
- audit / observability
- data-governance controls

The internal Growth Command Center is now implemented as a read-only localhost surface over the
existing operating data. This does not authorise a customer-facing control plane or autonomous
outreach: it proposes one next action and keeps contact, publishing, spend and contract changes behind
human approval.

## Digital marketing capability families

The authoritative, machine-readable list is `capability_map.json` (`make capability-map`), which
carries a build status per capability and is validated by `tests/test_capabilities.py`. The prose
below is a summary of it, not a second source of truth.

The project covers these families, but they are deliberately **not** V0 build commitments:

- market, competitor and customer intelligence
- positioning, offers, pricing and messaging
- SEO and AI-search visibility
- content and social distribution
- email and lifecycle marketing
- paid media across Google, Meta, LinkedIn, TikTok and other validated channels
- landing pages, lead capture and CRO
- creative strategy, AI UGC, video, hooks and mutation trees
- creative fatigue observability
- outbound, affiliates, referrals, influencers and partnerships
- CRM, nurture, retention and expansion
- attribution, CAC, LTV, contribution profit, pipeline and revenue measurement
- autonomous campaign optimisation
- Growth Event Bus
- generated internal tools

They remain marketing hypotheses until a market experiment or customer delivery exposes a repeated,
valuable workflow. Coverage means the project may operate in these areas; it does not authorise
speculative software construction.

## Operating patterns retained from research

- **Creative:** AI UGC, hooks, creative families, mutation trees and fatigue monitoring
- **Paid media:** Google/Meta/LinkedIn/TikTok optimisation, CAC, contribution-profit and scale gates
- **Ecommerce:** product research, offer stacks, storefront experiments and rapid test pages
- **Competitive marketing:** reverse engineering, pattern extraction, and offer/CTA analysis
- **Content:** content as market research, short-form testing and authority building
- **Social conversion:** profile surfaces, public-to-private conversation, audience capture and
  content-to-revenue lineage
- **Affiliate:** offer routing, partner distribution and attribution
- **AI operations:** skills, Growth Operator workflows, decision-latency reduction and controlled automation

These are available patterns inside the Digital Marketing Project. None is a product-feature
commitment without a falsifiable experiment or repeated paid delivery need.

## Experiment portfolio

IDs are `EXP-<NAMESPACE>-<NNNN>`. The namespace set is **enforced** by
`EXPERIMENT_NAMESPACES` in `src/ai_growth_engineering/models.py`, not just documented here — an
unknown namespace is rejected at preregistration. Adding a namespace means editing that set and this
table together.

| ID | Scope | Status |
| --- | --- | --- |
| `EXP-ACQ-0001` | UK Cyber/MSP teardown-led outbound | ACTIVE — no conclusion before 50 qualified sends |
| `EXP-ACQ-0002+` | Future market acquisition experiments | UNPLANNED — requires a separate premise and preregistration |
| `EXP-CREATIVE-*` | Creative and AI UGC experiments | UNPLANNED — evidence-triggered |
| `EXP-PAID-*` | Paid-media and creative-family experiments | UNPLANNED — evidence-triggered |
| `EXP-SEO-*` | Search and AI-search visibility experiments | UNPLANNED — evidence-triggered |
| `EXP-CONTENT-*` | Content-distribution experiments | UNPLANNED — evidence-triggered |
| `EXP-SOCIAL-*` | Social distribution and content-to-signal experiments | UNPLANNED — evidence-triggered |
| `EXP-PROFILE-*` | Social profile conversion experiments | UNPLANNED — evidence-triggered |
| `EXP-CONVERSATION-*` | Public-content to private-conversation experiments | UNPLANNED — evidence-triggered |
| `EXP-PARTNER-*` | Affiliate, referral and partnership experiments | UNPLANNED — evidence-triggered |
| `EXP-CRO-*` | Landing-page and conversion experiments | UNPLANNED — evidence-triggered |
| `EXP-EMAIL-*` | Email acquisition and lifecycle experiments | UNPLANNED — evidence-triggered |
| `EXP-LIFECYCLE-*` | Nurture, retention and expansion experiments | UNPLANNED — evidence-triggered |
| `EXP-OFFER-*` | Offer, pricing and messaging experiments | UNPLANNED — evidence-triggered |
