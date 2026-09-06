---
name: revenue-intelligence
description: "Turn observed commercial signals into internal prospect recommendations, preserving the path from signal to revenue. Triggers on: prioritising accounts, deciding who to contact now and why. Does NOT trigger on: sending anything, or optimising outreach volume. Produces: ranked buyer actions justified now, each traceable back to the signal that caused it."
metadata:
  mode: READ
  version: "1.0.0"
  last_reviewed: 2026-09-06
  forbidden:
    - recommend an action with no observed signal behind it
    - optimise for outreach volume rather than for justified actions
  evidence: every recommendation carries the full chain: observed signal, source, evidence, identity, gate, priority
  escalate_when: a recommendation would act on an identity the eligibility gate cannot confirm
  termination:
    - stop after the eligibility gate rejects 3 candidates for the same reason and report the pattern
    - stop after 1 ranking pass per signal refresh; the same signals return the same order
  verified_by: tests/test_revenue_signal_intelligence.py
---

# Revenue Intelligence

Use this skill when turning observed commercial signals into internal prospect recommendations.

## Objective

Find the highest-value buyer actions that are justified **now**, explain why, and preserve the path from observed signal to eventual revenue. Do not optimise for outreach volume.

## Required chain

```text
OBSERVED SIGNAL
→ SOURCE
→ EVIDENCE
→ IDENTITY
→ ELIGIBILITY GATE
→ PRIORITY
→ HUMAN REVIEW
→ ACTION
→ OUTCOME
→ REVENUE / CONTRIBUTION
```

## Signal rules

A signal is not a lead and not proof of pain. Record:

- signal type
- person/company
- source URL or first-party source
- observation date
- evidence id
- confidence
- strength 1–5
- commercial interpretation, explicitly as interpretation

Signals decay in priority with age but remain evidence.

## Eligibility before ranking

A candidate must pass every hard constraint:

- named buyer exists
- identity is verified or directly observed
- suppression/opt-out is clear
- ICP is eligible
- no hard disqualifier
- at least one evidence id exists
- a reachable channel is known

A high intent score cannot compensate for failure of any hard constraint.

## Priority

Rank only eligible candidates. Use bounded, explainable inputs:

- ICP fit
- signal strength
- signal confidence
- freshness
- evidence depth
- route quality

Every output must expose the component explanation. Never present the score as purchase probability.

## Identity and enrichment

Provider output is evidence about identity, not truth. Persist provider, source, confidence, verification state and reachable channel. Do not guess addresses merely to increase coverage.

## Recommendation object

The operator should see:

```text
WHO
WHY NOW
WHY FIT
EVIDENCE
UNKNOWNS
PRIORITY EXPLANATION
SUGGESTED ANGLE
CHANNEL
AUTHORITY
```

External contact remains `R3_APPROVAL_REQUIRED`. This skill may rank and recommend; it may not send.

## Learning

When outcomes exist, preserve lineage:

```text
SIGNAL
→ EVIDENCE
→ IDENTITY
→ OFFER
→ ANGLE
→ EXPERIMENT
→ CHANNEL
→ OUTCOME
→ REVENUE
→ CONTRIBUTION PROFIT
```

Optimise later for profitable customers subject to policy and trust constraints, not reply rate alone.

## Explicitly not implemented here

- external signal connectors
- enrichment-vendor adapters
- email or LinkedIn sending
- CRM write access
- cross-tenant learning
- autonomous follow-up

Those remain separate capabilities and require their own evidence, policy and integration tests.
