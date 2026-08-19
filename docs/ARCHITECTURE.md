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
