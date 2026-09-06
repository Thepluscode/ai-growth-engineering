---
name: experiment-design
description: "Preregister an experiment with its metric, sample, and both thresholds before it runs. Triggers on: proposing a test, designing a validation, setting a success or kill threshold. Does NOT trigger on: reading a finished result. Produces: a preregistration that cannot be edited after the outcome is seen."
metadata:
  mode: READ
  version: "1.0.0"
  last_reviewed: 2026-09-06
  forbidden:
    - change a threshold after observing the result — mark the experiment invalid instead
    - run an experiment with no kill threshold, which makes it unfalsifiable
  evidence: every experiment carries its id, evidence ids, baseline, minimum sample and both thresholds before the first observation
  escalate_when: the minimum sample cannot be reached within the available budget or window
  termination:
    - stop at the kill threshold, not at the point the result becomes disappointing
    - stop after 2 redesigns of the same hypothesis and escalate the hypothesis rather than the design
  verified_by: tests/test_registry.py
---

# Experiment Design

Every experiment must be preregistered.

Required:
- experiment_id
- evidence IDs
- hypothesis
- primary metric
- baseline
- minimum sample
- success threshold
- kill threshold
- guardrails

Never retroactively change thresholds after observing the result. Mark invalid instead.
