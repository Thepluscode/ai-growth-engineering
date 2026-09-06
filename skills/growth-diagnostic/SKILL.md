---
name: growth-diagnostic
description: "Diagnose the single highest-priority growth constraint in order: demand, discovery, positioning, conversion, qualification, handoff, economics. Triggers on: 'why is growth stalled', pipeline diagnosis, deciding what to fix first. Does NOT trigger on: executing a fix. Produces: one named constraint with its evidence, or an explicit insufficient-evidence verdict."
metadata:
  mode: READ
  version: "1.0.0"
  last_reviewed: 2026-09-06
  forbidden:
    - return more than one constraint — a list of seven problems is not a diagnosis
    - skip a stage because a later one looks more interesting
  evidence: the named constraint cites the stage metric that identified it, and every recommendation carries its thresholds
  escalate_when: two stages are equally constrained, or the data cannot separate them
  termination:
    - stop at the 1st stage that fails; later stages are downstream of it and their numbers are fiction
    - stop after 2 passes with insufficient evidence and return that verdict rather than a guess
  verified_by: tests/test_growthops.py
---

# Growth Diagnostic

Diagnose in this order:
1. demand
2. discovery
3. positioning / offer
4. conversion
5. qualification
6. sales handoff
7. economics

Return exactly one highest-priority constraint unless evidence is insufficient.

Every recommendation must include:
- evidence
- hypothesis
- primary metric
- minimum sample
- success threshold
- kill threshold
