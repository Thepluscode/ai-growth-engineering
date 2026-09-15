# Marketing Engineer — revenue loop architecture

**Status of this document:** Phase 0 inventory plus the first production slice (2026-09-15).
The capability map remains the architecture of record; this file explains how the revenue loop
fits into what already existed, and what was deliberately not built.

## The loop

```text
Evidence → Opportunity → ICP → Offer → Experiment → Campaign/Creative/Audience
→ FUNNEL EVENTS (append-only) → deterministic metrics → funnel → attribution → money graph
→ evaluation (rules) → next experiment (one preferred + alternatives) → human approval → execution
```

Every stage after execution reads one canonical record: `funnel_events`. Nothing downstream of it
stores its own copy of a count, a rate or an attributed amount.

## Phase 0 — inventory

### Existing components reused

| Component | Where | Used for |
|---|---|---|
| Evidence registry + observed/inference split | `models.Evidence`, `registry.add_evidence` | evidence cited by findings |
| Experiment contract, namespaces, preregistration | `models.ExperimentSpec`, `experiments` table | experiment state, thresholds, minimum sample |
| Non-compensatory decisions + trust guardrails | `registry.record_experiment_result`, `trust.py` | KEEP/ITERATE/REVIEW, guardrails listed in recommendations |
| Execution cohort + invitations | `execution.py` | frozen supply for EXP-ACQ-0003; adapter source |
| Outreach log import, recipient class, channel | `registry.import_outreach`, `outreach` table | adapter source; route split |
| Commercial funnel rates with honest zero denominators | `economics.funnel_rates` | the rule carried into every new metric |
| Unit economics (CAC incl. sales cost, contribution, LTV only with churn) | `economics.py` | unchanged; remains the scale gate |
| Operator next-move by constraint | `growthops._next_move` | precedent for the recommender |
| Offers, channels, creatives, attribution registries | `registries.py` | definitions; not duplicated |
| Human-gated authority, no autosend | `growthops`, `outbound_workbench`, `policies.py` | recommendations are data, never actions |

### Duplicated or overlapping concepts found

| Concept | Existing form | Problem | Resolution |
|---|---|---|---|
| Funnel stage counts | `outreach` row flags (`meaningful_reply`, `discovery`, `proposal`, `paid`, `collected_revenue_pence`) | mutable, no timestamps per stage, no experiment id, no correction history | kept as the legacy send log; events are derived from its source CSV by an idempotent adapter |
| Aggregate outcome columns | `creatives`, `social_profiles`, `conversation_funnels`, `angles` carry `qualified_leads`, `revenue_pence` | counts typed into a definition row drift from what happened | left in place; the revenue loop never reads them. Retire when an adapter feeds events for those surfaces |
| Attribution | `attribution` registry (one row, `touchpoint_path` text) | no model, no weights, cannot be recomputed | attribution is now **derived** from events on read (first/last/linear); the registry stays for manually recorded partner attribution |
| Access outcomes | `invitations` (updated in place) | an acceptance can silently become a withdrawal | adapter appends `invitation_accepted` and appends a correction when the table later disagrees |
| Imported Marketing Engineering OS (`imports/`, local only) | exposure/outcome schemas, origin × claim-domain admissibility, audit log | a second architecture in a second stack | not merged into the engine; its ideas are reflected here (one canonical event, provenance on every row, synthetic never validates). Its live experiments are recorded as EXP-ACQ-0005/0006 |

### Genuinely missing (and now built)

1. **Canonical, append-only funnel event log** with correction events, provenance and idempotent ids — `funnel_events.py`, `storage.SCHEMA`.
2. **Adapters from real stores to events** — outreach send log, invitation cohort.
3. **Deterministic metric definitions** stored beside every value (CPM, CTR, CPC, hook rate, landing-page CVR, lead CVR, qualified-lead rate, accept rate, meaningful reply rate, meeting/proposal/close rates, CPL, qualified CPL, cost per meeting, CAC, ROAS, pipeline ROAS) — `revenue_loop.METRICS`.
4. **Funnel analytics** by any event column or `metadata.<key>` and date range.
5. **Explicit attribution models** — first touch, last touch, linear, whole-pence shares.
6. **Money graph** — buyer → every touch, campaign, experiment arm, revenue, CAC per campaign; campaign → spend, pipeline, customers, attributed revenue, ROAS per model.
7. **Evaluator** — rule-based findings with observation, evidence, interpretation, action, single test variable, primary metric and why not another metric.
8. **`recommend_next_experiment()`** — exactly one preferred experiment plus alternatives, all required fields.
9. **Single declared variable** on the experiment contract — `ExperimentSpec.variable`.
10. **`age marketing-engineer status`** — the eight questions, each answer labelled OBSERVED, DERIVED, INTERPRETATION or RECOMMENDATION.

## Source-of-truth boundaries

| Truth | Owner | Never |
|---|---|---|
| What happened (sends, replies, meetings, proposals, wins, payments, spend) | `funnel_events` | updated or deleted; a correction is appended |
| What things are (offers, channels, creatives, claims, evidence) | registries | used to hold outcome counts the loop reads |
| What an experiment promised to test | `experiments` contract, frozen before exposure | changed after exposure |
| Metrics, funnels, attribution, money graph | computed on read from effective events | stored as truth, or produced by a model |
| Interpretation and recommendation | `marketing_engineer.py`, labelled `deterministic_rules` | executed; every external action stays behind human approval |

Synthetic fixtures carry `provenance = synthetic_fixture` and are excluded from every total unless
explicitly requested, so demonstration data can never read as market validation.

## Adapter contract

```text
external or legacy record → validate → canonical funnel event (source, source_record_id, provenance)
```

An adapter never supplies a field its source does not carry (a send log with no reply date keeps
`occurred_at_is_send_date: true`) and never assigns an experiment the source does not name — the
operator passes `--experiment-id`.

## Deliberately not built yet

Per the founder's sequencing — money lineage on one real channel first, paid channels after it works:

- Platform adapters (Meta, Google Ads, LinkedIn Ads, GA4, Stripe, HighLevel, calendar). The event
  vocabulary and metric definitions accept their data; no adapter exists until a real account does.
- Creative-fatigue classification (needs windowed frequency/CTR/CPC observations that do not exist).
- Retargeting and lookalike audience records (must come from a platform, never be invented).
- Campaign and audience registries (no budget or platform audience exists to register).
- LLM interpretation. This repository has no model integration; the evaluator is deterministic
  rules. A model may later explain findings, never compute or change a metric.
- Observed LTV from events (no recurring revenue data; `economics.ltv` stays the only LTV and
  returns None without churn).
