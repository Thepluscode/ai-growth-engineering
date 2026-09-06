---
name: customer-intelligence
description: "Extract the buyer's own problem, language, objections and buying role from supplied evidence. Triggers on: customer interviews, reviews, call notes, support threads, win/loss material. Does NOT trigger on: writing copy, or inventing a persona with no source. Produces: a structured buyer record where every verbatim quote is source-backed."
metadata:
  mode: READ
  version: "1.0.0"
  last_reviewed: 2026-09-06
  forbidden:
    - manufacture a buyer quote, or store one with no source
    - record a desired outcome the buyer did not state as one they did
  evidence: every field cites the source it was extracted from, and quotes are stored verbatim or not at all
  escalate_when: the evidence contains no first-party buyer voice, only commentary about buyers
  termination:
    - stop after 2 passes over one evidence set; a 3rd rephrases rather than extracts
    - stop after 3 sources yield no economic consequence and report the pain as unqualified
  verified_by: none - extraction discipline; the no-manufactured-quote rule is not machine-checked
---

# Customer Intelligence

Extract:
- problem
- symptom
- trigger
- economic consequence
- current workaround
- failed alternative
- desired outcome
- exact language
- objection
- proof required
- buying role

Never manufacture a buyer quote. Store verbatim quotes only when source-backed.
