---
name: market-research
description: "Find demand evidence for a problem hypothesis, not interesting facts about a market. Triggers on: sizing a problem, testing whether demand exists, sourcing signals for an ICP. Does NOT trigger on: competitor feature comparison or general industry reading. Produces: observed signals with sources and confidence, plus the uncertainties that remain."
metadata:
  mode: READ
  version: "1.0.0"
  last_reviewed: 2026-09-06
  forbidden:
    - present an inference as an observed signal
    - report a market as validated on aggregator content with no primary source
  evidence: every signal names its source and its confidence, and inferences are labelled as inferences
  escalate_when: all agreeing sources are aggregators, or the primary source contradicts them
  termination:
    - stop once 3 independent sources agree and at least 1 is primary; a 4th aggregator adds no information
    - stop after 2 failed attempts to reach a primary source and mark the signal unverified
  verified_by: tests/test_signal_intelligence.py
---

# Market Research

## Purpose
Find demand evidence, not interesting facts.

## Inputs
- ICP
- problem hypothesis
- geography
- current offer

## Output schema
- observed signals
- sources
- confidence
- buyer problem
- economic consequence
- existing alternatives
- uncertainties
- experiment candidates

## Hard rules
- Separate observation from inference.
- Do not infer profitability from visible ads or revenue screenshots.
- Prefer two independent demand signals before recommending a major asset build.
