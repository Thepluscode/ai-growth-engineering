# Digital Marketing Project Architecture

## Project boundary

Digital Marketing is the operating domain. AI Growth Engineering is the methodology and engineering
layer used to make work across that domain measurable, repeatable and safely automatable.

```text
DIGITAL MARKETING PROJECT
│
├── 1. MARKET INTELLIGENCE
│   ├── market and competitor research
│   ├── customer intelligence
│   └── demand discovery
├── 2. STRATEGY
│   ├── segmentation, brand and positioning
│   ├── offers and pricing
│   └── messaging
├── 3. CREATIVE
│   ├── copy, images, UGC and video
│   └── hooks and creative testing
├── 4. DISTRIBUTION
│   ├── SEO, AI search, social and content
│   ├── public content to private conversation
│   ├── email, paid media and outbound
│   └── affiliates, creators and partnerships
├── 5. CONVERSION
│   ├── ecommerce, landing pages, social profiles and CRO
│   ├── conversation funnels and audience capture
│   └── capture, qualification and booking
├── 6. REVENUE
│   ├── marketing automation, CRM and sales handoff
│   └── value ladders, retention and expansion
├── 7. MEASUREMENT
│   ├── attribution, CAC and LTV
│   └── contribution profit, pipeline and revenue
└── 8. AI GROWTH ENGINEERING
    ├── skills, agents and automation
    ├── experiments and evidence
    └── policies and control plane
```

## The capability map is the architecture of record

`capability_map.json` holds all 164 capabilities of the Digital Marketing Project across the eight
domains above, each with an honest build status: `IMPLEMENTED` (code exists and a deterministic test
covers it), `SPECIFIED` (written as a skill, template or policy but not executable), `HYPOTHESIS`
(named and understood, nothing built).

```bash
make capability-map     # current: IMPLEMENTED 61 · SPECIFIED 19 · HYPOTHESIS 84
```

Scope is declared in that file, **not** in empty directories. A directory appears when a capability
reaches `IMPLEMENTED`; an empty package is a claim the repository cannot back, and it makes the
architecture look built when it is not. Promotion out of `HYPOTHESIS` requires a market experiment or
a repeated paid delivery need.

## The engine is market-neutral

`src/`, `skills/`, `policies/`, `templates/` and `tests/` must work unchanged for a paid-media, SEO or
creative experiment. Market-specific vocabulary — a vertical, a company name, a channel assumption —
belongs under `experiments/<EXP-ID>/`.

`scripts/scope_gate.py` enforces this and runs in `make test` and CI. It has a `--selftest` that
proves it can fail, and it has been observed failing against a real leak planted in `src/`.

## Build principle

The first engineering component is an **evidence operating system**, not a customer-facing SaaS.

```text
MARKET / CUSTOMER EVIDENCE
          ↓
      OBSERVATION
          ↓
      HYPOTHESIS
          ↓
      EXPERIMENT
          ↓
QUALIFIED PIPELINE / REVENUE
          ↓
       LEARNING
          ↺
```

## Control-plane boundary

Every action-producing skill is separated from authority.

```text
GROWTH OPERATOR
      ↓
    SREVIEW
      ↓
PROPOSED ACTION
      ↓
CONTROL PLANE
  Identity
  Policy
  Evidence
  Budget
  Claims
  Approval
      ↓
ALLOW / DENY / ESCALATE
      ↓
    ACTION
      ↓
     AUDIT
```

## V0 components

1. Prospect registry
2. Evidence registry
3. Growth Leak Teardown generator
4. Experiment registry with preregistration
5. Outreach/revenue scoreboard
6. Suppression registry
7. Rule-of-One and demand gates
8. Growth action authority policy

These components currently support `EXP-ACQ-0001`, a UK Cyber/MSP acquisition experiment. The
experiment is one bounded use of the architecture; it does not define the markets or channels the
Digital Marketing Project may test next.

## V0.2 structural contracts

The first cross-channel architecture is intentionally schemas and deterministic interfaces, not
channel automation.

### Software-memory registries

`registries.py` defines the repeated schemas; customer evidence and experiments retain specialised
validation interfaces. Together they provide twenty-two registries:

1. Customer evidence
2. Offers
3. Proof inventory
4. Creatives
5. Channels
6. Experiments
7. Competitor patterns
8. Claims
9. Partners
10. Revenue attribution
11. Social profile surfaces
12. Conversation funnels
13. Audience ownership
14. Value ladders
15. Voice of customer
16. Angles
17. Belief shifts
18. Psychological drivers
19. Scarcity claims
20. Economics
21. Product opportunities
22. Product format decisions

Evidence keeps the observed statement, inference, confidence, observation date and commercial
implication separate. Structured metadata preserves voice-of-customer context such as audience,
problem, trigger, fear, desired outcome, objection, exact language and commercial intent.
Experiment-to-evidence links are relational and foreign-key constrained.

### Product opportunity contract

Ideas do not become build commitments through an average score. `ProductBuildGate` requires every
candidate to name a buyer, problem, minimum evidence set, positive demand signal, viable distribution
path, measurable purchase action, fixed validation test, and economics hypothesis. A missing input
returns the candidate to research; margin and excitement cannot compensate.

Only gate-passing candidates can be ranked. The rank compares pain, frequency, urgency, buying
intent, economic value, distribution access, and evidence strength against build, delivery, support,
and validation costs. The lineage is preserved end to end:

```text
IDEA → EVIDENCE → OPPORTUNITY → OFFER → MINIMUM COMMERCIAL UNIT
     → PURCHASE → USAGE → OUTCOME → EXPANSION
```

`ProductFormatSignals` chooses the smallest justified format from recurrence, changing data, saved
state, automation, integration, and ongoing value. Productisation proceeds from insight through
manual delivery before software. Failed tests enter the Opportunity Graveyard with a reason, date,
and observable reopen condition; ideas are preserved, not deleted.

### Universal experiment contract

Every namespace uses `ExperimentSpec`: market, buyer, problem, channel, hypothesis, supporting
evidence, control, variant, primary/secondary/economic metrics, sample, budget, thresholds, dates,
decision and learning. The same contract accepts acquisition, content, creative, CRO, social,
profile, conversation, email, lifecycle, offer, paid-media, partner and SEO experiments.

### Social conversion contract

Social content, the profile, private conversation, contact capture and lifecycle are measured as one
conversion system rather than separate channel activities:

```text
CONTENT_ID
    ↓
VIEW → PROFILE → DM → LEAD → QUALIFIED → OPPORTUNITY → CUSTOMER → REVENUE
                         ↓
                  OWNED CONTACT
                         ↓
                RETENTION / EXPANSION
```

`social_profiles` stores platform, audience, positioning, bio promise, CTA, pinned content, proof,
link and DM paths plus downstream outcomes. `conversation_funnels` links the originating content to
the engagement trigger, DM path, qualification, capture destination, offer and revenue.
`audience_ownership` distinguishes qualified rented-platform interactions from captured contacts.
`attribution` carries the content, profile, conversation, audience, offer and customer identifiers so
revenue can be traced across the whole path.

`social.py` computes profile-visit rate, DM-start rate, qualified conversations per thousand views,
audience capture rate and revenue per thousand views. `economics.py` adds realised 30-, 90- and
365-day customer value, gross profit per acquired customer and expansion rate. Missing denominators
return unknown rather than a misleading zero.

The architecture supports `EXP-SOCIAL-*`, `EXP-PROFILE-*` and `EXP-CONVERSATION-*`; lifecycle tests
continue under `EXP-LIFECYCLE-*`. It does not assume a particular social platform is best and does
not authorise comment-to-DM automation or unsolicited messaging.

### Content-to-offer evidence loop

```text
HYPOTHESIS → CONTENT → AUDIENCE REACTION → CONVERSATION
     ↑                                      ↓
COMMERCIAL DECISION ← OFFER HYPOTHESIS ← VOC EVIDENCE
```

Social polls, comments, DM conversations and story responses enter the existing customer-evidence
model. They are sources, not proof by themselves; observation, exact language and inference remain
separate.

### Economics decision layer

`economics.py` uses integer pence to calculate gross profit, acquisition cost, contribution profit,
CAC, churn-based LTV, realised lifecycle value, payback and allowable CAC. Its scale verdict
distinguishes `SCALE`, `HOLD`, `REVIEW` and `INSUFFICIENT_DATA`, so missing measurements cannot be
mistaken for either success or failure.

The implementation order remains manual → measured → repeated → standardised → automated →
agentic. These contracts do not authorise channel integrations or autonomous actions.

## Deliberately absent

- autonomous ad buying
- CRM integrations
- Meta/Google/LinkedIn write access
- AI-generated bulk outreach
- autonomous social messaging or comment-to-DM automation
- customer-facing dashboard
- Growth Command Center
- proprietary SaaS

Those require repeated paid workflow evidence first.
