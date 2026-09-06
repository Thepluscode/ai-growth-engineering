---
name: outreach-research
description: "Build one account-level outreach message from an observable commercial signal, and score it before it sends. Triggers on: researching an account, drafting outbound, scoring a message for send eligibility. Does NOT trigger on: bulk sending or list building. Produces: one message with a quality score, where below 18 does not send."
metadata:
  mode: GENERATE
  version: "1.0.0"
  last_reviewed: 2026-09-06
  forbidden:
    - send or mark send-eligible a message scoring below 18
    - assert a commercial signal that was not observed on a named source
  evidence: every claim in the message traces to an observed signal with its source, and the score records all six components
  escalate_when: the score lands in the 18-23 review band, or the signal is older than the buying cycle it assumes
  termination:
    - stop after 2 rewrites fail to reach 24; the signal is the problem, not the wording
    - stop after researching 1 account per pass — a 2nd account in the same pass reuses the first one's framing
  verified_by: tests/test_outreach.py
---

# Outreach Research

Build one account-level message from:
- ICP fit
- observable commercial signal
- plausible problem
- evidence confidence
- one low-friction CTA

Quality score:
- ICP fit 0–5
- decision-maker fit 0–5
- research evidence 0–5
- pain relevance 0–5
- message specificity 0–5
- CTA friction 0–5

<18: do not send
18–23: review
24+: send eligible

Never send to a suppressed identity.
