---
name: experiment-design
description: "Preregister an experiment with its single variable, metric, sample, and both thresholds before it runs. Triggers on: proposing a test, designing a validation, setting a success or review threshold. Does NOT trigger on: reading a finished result. Produces: a preregistration that cannot be edited after the outcome is seen."
metadata:
  mode: READ
  version: "1.1.0"
  last_reviewed: 2026-09-15
  forbidden:
    - change a threshold after observing the result — mark the experiment invalid instead
    - run an experiment with no review threshold, which makes it unfalsifiable
    - call a difference caused unless it came from concurrent arms of one experiment differing only in the declared variable
  evidence: every experiment carries its id, evidence ids, baseline, single variable, minimum sample and both thresholds before the first observation
  escalate_when: the minimum sample cannot be reached within the available budget or window
  termination:
    - stop at the review threshold and hand the result to a person, not at the point the result becomes disappointing
    - stop after 2 redesigns of the same hypothesis and escalate the hypothesis rather than the design
  verified_by: tests/test_registry.py, tests/test_procedures.py
---

# Experiment Design

Every experiment must be preregistered.

Required:
- experiment_id
- evidence IDs
- hypothesis
- one declared variable (a procedure version counts as one)
- primary metric tied to a buyer outcome, never to activity (messages, posts, impressions, experiments launched)
- baseline
- minimum sample
- success threshold
- review threshold
- guardrails

Never retroactively change thresholds after observing the result. Mark invalid instead.

Reading the result (v1.1.0, mined from the 2026-09-15 comparison in `docs/PROCEDURE_GAP_REVIEW.md`):
- No verdict before the minimum sample, and none on exposures still inside the response window.
- The denominator is delivered exposure; a bounce or undeliverable attempt is not exposure.
- A non-significant result at a sample that could not see a meaningful gap is underpowered, not "no difference".
- A guardrail breach sends a winning result to review; the primary metric cannot buy it back.
- A winner holds for that experiment's buyers; applying it elsewhere is a new experiment.
