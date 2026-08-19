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
│   ├── email, paid media and outbound
│   └── affiliates, creators and partnerships
├── 5. CONVERSION
│   ├── ecommerce, landing pages and CRO
│   └── capture, qualification and booking
├── 6. REVENUE
│   ├── marketing automation, CRM and sales handoff
│   └── retention and expansion
├── 7. MEASUREMENT
│   ├── attribution, CAC and LTV
│   └── contribution profit, pipeline and revenue
└── 8. AI GROWTH ENGINEERING
    ├── skills, agents and automation
    ├── experiments and evidence
    └── policies and control plane
```

## The capability map is the architecture of record

`capability_map.json` holds all 122 capabilities of the Digital Marketing Project across the eight
domains above, each with an honest build status: `IMPLEMENTED` (code exists and a deterministic test
covers it), `SPECIFIED` (written as a skill, template or policy but not executable), `HYPOTHESIS`
(named and understood, nothing built).

```bash
make capability-map     # current: IMPLEMENTED 21 · SPECIFIED 9 · HYPOTHESIS 92
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
    SKILL
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

## Deliberately absent

- autonomous ad buying
- CRM integrations
- Meta/Google/LinkedIn write access
- AI-generated bulk outreach
- customer-facing dashboard
- proprietary SaaS

Those require repeated paid workflow evidence first.
