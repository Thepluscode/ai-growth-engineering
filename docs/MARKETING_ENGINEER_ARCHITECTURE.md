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

## Marketing procedures — approved skills as experimental inputs (2026-09-15)

```text
Intelligent Machine (admission, provenance, permissions, approval — NOT reproduced here)
   │  approved-skill-export.v1 (file snapshot, no runtime coupling)
   ▼
procedures registry (procedure_id@version + content_hash)     = KNOWN, never PROVEN
   ▼
experiment_procedures (frozen before first exposure)           = VARIABLE of one arm | COMMON_INPUT of every arm
   ▼
canonical funnel events (unchanged) → segment unit model → change_diagnosis window resolution
   ▼
procedure evaluator (on read) → report + skill-evaluation-result.v2 → back to the Intelligent Machine as evidence

Intelligent Machine revokes / withdraws → `make external-skills-publish` replaces contracts/exports/<id>.json
with skill-revocation.v1 → AGE re-reads that path before every NEW declaration
```

| Truth | Owner | Never |
|---|---|---|
| Whether an external skill may be used | Intelligent Machine | re-reviewed, widened or approved here |
| Which procedure version exists | `procedures` registry | carrying a score, lift or revenue field |
| Which version an experiment ran | `experiment_procedures`, append-only, refused after exposure | inferred from timing or backfilled |
| Whether it performed better | `procedures.evaluate`, computed on read | stored, or produced by a model |

**Import** (`age procedures import FILE`) refuses, in order: an unsupported contract or version, an
admission status other than APPROVED, a revoked or unadopted skill, a missing or malformed sha256,
missing provenance (source type, commit, licence, repository or URL, approver, approval date), use
cases that do not permit marketing, an expired review, and anything off the vendored schema
(`src/ai_growth_engineering/contracts/`, copied from the Intelligent Machine at 0cddae4). The same file
re-imports to the same row; the same version with different content is refused.

**Baseline.** ThePlus's own `skills/*/SKILL.md` are the baseline procedures, seeded in
`seeds/registries.json` with the hash of each file; a test fails if a skill file changes without a
version bump.

**Declaration** (`age procedures bind`). A procedure is the experimental VARIABLE only when the frozen
contract declares `variable = procedure`; otherwise it is a COMMON_INPUT held constant. Once any
exposure exists the declaration is refused, and a different version or hash for an arm is refused at
any time: a new version is a new experiment.

**Upstream approval at declaration (fail closed).** An import is a snapshot. Before every NEW
declaration of an approved external procedure, `upstream_refusal` refuses when:
- the file now holds the Intelligent Machine's `skill-revocation.v1` notice for that exact identity (`upstream_revoked`); a notice for another identity, or an invalid one, is `upstream_approval_not_current`;
- the stored `review_after` has passed (`review_expired`), even if the upstream export was re-reviewed since, because nothing is silently refreshed;
- the export file it was imported from is gone (`upstream_export_missing`);
- that file no longer passes import (`upstream_approval_not_current`), for example no longer APPROVED, revoked, or its marketing use case removed;
- it now names a different id or version (`upstream_identity_changed`) or content hash (`upstream_content_changed`);
- a use case approved at import has been withdrawn (`upstream_use_case_withdrawn`).

Declarations already made are history: they are never re-judged, rewritten or deleted. A ThePlus
baseline has no upstream approval to lapse.

**The revocation signal only reaches the file it replaces.** The Intelligent Machine's `make
external-skills-publish` writes a revocation or withdrawal notice over `contracts/exports/<skill_id>.json`.
Import therefore accepts only that governed file: `governed_export_path(skill_id)` is the resolved
`AGE_SKILL_EXPORTS_DIR` (default: the sibling Intelligent Machine checkout's
`agentic-os/external-skills/contracts/exports`) plus `<skill_id>.json`. Anything else is refused
(`not_the_published_export`). That includes a copy kept under the same `…/contracts/exports/` shape
somewhere else, and a symlink planted at the governed name.

A new declaration re-checks the stored origin against the governed path. A procedure imported
anywhere else, or whose governed directory has since moved, is refused (`untrusted_export_origin`).

**P2: MANAGED_EXPORT_ORIGIN_ENFORCEMENT — closed (2026-09-15).** The origin is enforced by a configured
trust anchor: no signing, no server, and no runtime coupling. Only the local file path is read, as
before. Existing declarations are never re-judged.

**Result validation is version-selected.** `validate_result` reads the document's own `contract`:
`skill-evaluation-result.v1` against the v1 pin, `.v2` against the v2 pin, anything else unsupported.
AGE emits v2 only. A v1 document may carry an offline or descriptive result; it can never carry a
causal class, market validation or KEEP, because v1 does not record competing variables or synthetic
exposure and nothing absent is inferred.

**Pinned contracts.** `SCHEMA_PINS` in `procedures.py` holds the sha256 of all four shared contracts:
- export v1 `f6665386…`
- result v1 `9880e22b…`, kept byte-for-byte and no longer emitted
- result v2 `0ee7e90f…`, emitted
- revocation v1 `fe5a5ea9…`

A schema whose bytes differ from its pin validates nothing (`schema_drift`). A test compares the pins
with the Intelligent Machine's committed copies. A contract change is a new version, never an
in-place edit.

**Lineage.** An event runs under a procedure only through its own experiment's declaration for its
arm (or every arm) made on or before the day it happened. Exposures dated before the declaration, and
events whose metadata records a different `procedure_ref`, break the comparison.

**Evaluation** (`age marketing-engineer procedure`). The metric is the experiment's preregistered
primary metric, never chosen at read time; activity metrics are refused and jobs judged offline
(buyer research, experiment design and analysis, RevOps) are NOT_EVALUABLE in the market. Classes, in
order: NOT_EVALUABLE (no declaration, no market exposure — synthetic fixtures never count — or no
delivered exposure) → IMMATURE → CONFOUNDED (a recorded input other than the job's own output
changed, sides not concurrent, exposure before declaration, competing procedure) →
INSUFFICIENT_SAMPLE (below 30 matured per side or the preregistered minimum, zero outcomes on both
sides, or underpowered: the smallest visible gap exceeds 10 points) → CONTROLLED_EFFECT / REGRESSION
(only a CONTROLLED_MARKET_EXPERIMENT: one experiment, variable = procedure, both arms declared) or
DESCRIPTIVE_DIFFERENCE (observational) → NO_DIFFERENCE. Decisions: KEEP only on CONTROLLED_EFFECT;
REJECT on REGRESSION or a powered NO_DIFFERENCE (the baseline is retained); ITERATE on descriptive or
confounded; NEED_MORE_DATA otherwise. Revenue is reported per side through the same unit model with
the money-graph campaigns to open, and is ASSOCIATED_ONLY unless a controlled experiment's primary
metric was paid rate.

**Result export** (`--export FILE`, `age procedures validate-result FILE`). `skill-evaluation-result.v2`
re-checks the evaluator's own controlled-effect requirements on the document itself, so a hand-edited
or foreign result cannot carry a claim its evidence does not support.
- **CONTROLLED_EFFECT or REGRESSION** requires:
  - a CONTROLLED_MARKET_EXPERIMENT and a non-null experiment id;
  - exact, distinct candidate and baseline identities;
  - no competing variables and no synthetic data;
  - 30+ matured exposures per side, in a MATURE or PARTIALLY_MATURE state;
  - a market primary metric whose difference passes z 1.96 in the stated direction.
- **Revenue claim** is a closed enum: NONE_OBSERVED / ASSOCIATED_ONLY / ATTRIBUTED / CAUSAL_SUPPORTED.
  - CAUSAL_SUPPORTED requires a CONTROLLED_EFFECT whose primary metric is a paid outcome.
  - An offline evaluation can only claim NONE_OBSERVED.
- **market_validation** requires a controlled effect and is refused for offline or synthetic evidence.
- **KEEP** requires a controlled effect.
- **Authority** must be RECOMMENDATION_ONLY.

```text
External skill adoption is not market validation.
Offline eval is not revenue evidence.
Correlation is not controlled effect.
Higher activity is not better growth.
Procedure competence does not grant execution authority.
```

No autonomous learning mutation exists: an underperforming procedure is never rewritten, committed or
promoted here. The path is outcome → proposed improvement → new version and hash → offline evaluation
→ controlled experiment where justified → human review in the Intelligent Machine → new approved
version. The candidate review behind this build is `docs/PROCEDURE_GAP_REVIEW.md`.

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
