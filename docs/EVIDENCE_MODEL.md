# Evidence Model

## Evidence classes

- `observation`: directly visible fact
- `customer_quote`: exact customer/prospect language
- `crm`: internal commercial record
- `analytics`: measured funnel/platform data
- `experiment`: controlled result
- `third_party`: reputable external evidence
- `inference`: explicit interpretation, never stored as observation

## Rule

Every material claim must preserve:

```text
SOURCE
↓
EVIDENCE
↓
INFERENCE (if any)
↓
HYPOTHESIS
↓
EXPERIMENT
↓
RESULT
↓
COMMERCIAL CLAIM
```

Unsupported claims are blocked from publication.

## Social voice-of-customer sources

Social polls, comments, DM conversations and story responses may enter the evidence registry. Store
the observable statement and exact language as evidence; store any diagnosis or commercial meaning
separately as inference. Structured metadata may carry:

```text
audience · problem · trigger · fear · desired outcome · objection
exact language · commercial intent
```

A creator claim, revenue screenshot or platform-growth anecdote is third-party input, not a system
assumption. It cannot become a publishable performance claim without source, period, cost,
attribution, profit context and verification.
