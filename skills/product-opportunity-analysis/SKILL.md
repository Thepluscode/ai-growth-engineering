---
name: product-opportunity-analysis
description: Evaluate evidence-backed product opportunities, select the smallest justified delivery format, and park failed ideas with reopen conditions. Use when deciding what to validate or build; do not use for unconstrained idea generation.
---

# Product Opportunity Analysis

Turn accumulated market evidence into a validation portfolio. Do not turn interesting ideas into
software commitments.

## Procedure

1. Gather existing evidence IDs. Separate observed facts, inferences, and unknowns; do not invent
   buyers, demand, willingness to pay, or distribution access.
2. Create a `ProductOpportunity` for each evidence-bearing candidate.
3. Run `ProductBuildGate` before scoring. Buyer, problem, the evidence threshold, demand signal,
   distribution path, measurable purchase action, validation test, and economics hypothesis are all
   mandatory. A high margin or exciting concept cannot compensate for a missing premise input.
4. Keep failures in `research`. If a fixed validation test fails, move the idea to `graveyard` with
   reason, decision date, and an observable reopen condition. Never delete it.
5. Rank only gate-passing candidates with `rank_opportunities`. Validate at most the top three; do
   not build a long list of ideas.
6. Choose format after the problem is supported. Use `ProductFormatSignals`: recurrence, changing
   data, saved state, automation, integration, and ongoing value. Mostly no means a static asset or
   manual service. Repeated dynamic value may justify a tool, software, or subscription.
7. Climb the productisation ladder only as evidence demands:

   `insight → content → free tool → paid asset → manual service → repeatable workflow → automation → software → platform`

8. Persist durable rows in `seeds/registries.json` under `product_opportunities` and
   `product_format_decisions`. Preserve evidence IDs and the decision.

## Output

- observed evidence and IDs
- inference and unknowns
- hard-gate result with every missing field
- score only when eligible
- proposed validation and measurable purchase action
- smallest justified format
- status: research, validate, build, or graveyard
- graveyard reason and reopen condition when parked

The Growth Command Center is outside this workflow. It remains backlog until repeated, trustworthy
operating data makes a dashboard useful rather than decorative.
