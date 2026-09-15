# Procedure gap review — external marketing procedures vs the ThePlus baseline (2026-09-15)

**What this is:** a bounded structural review, by a model, of public procedure patterns against what
this repository actually does. It chooses what to build. It is not market evidence, not revenue
evidence, and not an admission decision: admission belongs to the Intelligent Machine.

**Research budget (Rule 0.11).**
- **Question:** do publicly verifiable procedures in five areas contain a step this repository lacks that would improve customer truth, qualification, experiment quality, pipeline, attribution or learning speed?
- **Decision it unblocks:** which gaps, if any, to build in this slice.
- **Scope:** five public skill files pinned to one commit, plus the Intelligent Machine's candidate registry.

## What was and was not examined

| Source | State on 2026-09-15 | Examined? |
|---|---|---|
| AgentVolt candidates in the Intelligent Machine (`agentvolt_demand_generation`, `_revenue_operations`, `_context_engine`, `_iso42001_compliance`, `_skill_auditor`) | all DISCOVERED; source, licence, commit and content hash unknown; `export_document()` returns None for every one (checked against IM commit 0cddae4) | **No.** No listing was verified: the Intelligent Machine blocks external web research, and this session's web search budget was exhausted before a listing could be found. Nothing here says anything about AgentVolt's content. |
| [`coreyhaines31/marketingskills`](https://github.com/coreyhaines31/marketingskills), MIT, commit `5b2c0007766c6a1cf1d53fd8fc73e979e0821022` | public and open source; used as the verifiable stand-in for the same five areas | **Yes**, five `SKILL.md` files, sha256 below |

| Public skill | Version | sha256 | Area |
|---|---|---|---|
| `skills/cold-email/SKILL.md` | 2.0.0 | `b7f8d793169a5111c857e5720c6b80028686cc95d5a0d0d6570957c2710aff9e` | demand generation |
| `skills/customer-research/SKILL.md` | 2.0.2 | `ae4769147f63dd5aea1308a0fddd85473601164893f58111dce738738226317e` | customer research |
| `skills/revops/SKILL.md` | 2.0.0 | `bb27b16ad41c5c2d4fea14c12359c6a01fc755f2bb91140f0c2c43b05b3adb10` | revenue operations |
| `skills/ab-testing/SKILL.md` | 2.0.0 | `1fd229160f6014f3f2d7c92cc7d2f991fbf8dc9ed68aac9793c71b408a6d1144` | experiment design |
| `skills/product-marketing/SKILL.md` | 2.1.0 | `6dfd6bd485f62448385844cb9eceefcee0977c843d7a1c9e6077590d4e19d1ec` | context management |

None of these is admitted in the Intelligent Machine, so none can be imported or declared into an
experiment here. That is the system working, not a gap.

## Gap matrix

| Capability | Current ThePlus implementation | External pattern | Genuine gap? | Evidence | Decision |
|---|---|---|---|---|---|
| Outbound message procedure | `skills/outreach-research` (six-part score, <18 never sends, observed signal required, one CTA, suppression); human-approved reply capture | `cold-email`: peer voice; personalisation must connect to the problem ("remove it and the email still makes sense" = failing); 2–4 word subject lines | Not proven. The writing rules may change qualified replies; nothing shows they do | ThePlus has 0 qualified replies to compare against; the external file cites no outcome data for its own rules | **RUN_EXPERIMENT**, only after IM admission, declared as `variable = procedure` for `message_generation` |
| Follow-up sequences | none, by founder decision (no outbound sequencer) | `cold-email`: 3–5 emails, increasing gaps, breakup email | No: excluded by decision | Founder standing instruction; `GrowthActionPolicy` bulk outreach needs approval | **REJECT** |
| Customer research provenance | `skills/customer-intelligence` + `buyer_truth.py`: verbatim, source-linked, append-only, observation separate from interpretation, SEGMENT_CANDIDATE only at 3+ organisations, stalled objections at 2+ | `customer-research`: High/Medium/Low confidence by independent sources; unprompted language; recency weighting; sample-bias checks; no persona under 5 data points | No for confidence and provenance: ThePlus enforces them in code, the external skill asks the writer to | `buyer_truth.SEGMENT_MIN_ORGANISATIONS`, `linked_observation_frozen` trigger, `tests/test_buyer_truth.py` | **ALREADY_STRONGER** |
| Say-versus-do contradiction and recency | not built: buyer truth never compares what a buyer said with what the funnel shows they did, and never ages a statement | `customer-research`: flag contradictions; weight the last 12 months | Yes, small | 0 commercial evidence rows in the real store today, so it would find nothing | **MINE_PATTERN**, not built. Revival: evidence from 3+ organisations |
| Lead lifecycle and stage metrics | `funnel_events` stages, `revenue_loop.diagnose_funnel`, first/last/linear attribution, money graph | `revops`: stage definitions with entry and exit criteria, stage conversion, time in stage | No: the canonical event log already defines stages and conversion | `funnel_events.STAGES`, `tests/test_revenue_loop.py` | **ALREADY_STRONGER** |
| Stage hygiene diagnostics | not built: nothing flags a reply with no follow-up, a proposal with no meeting, or a stage held too long | `revops`: stale-deal alerts, stage-skip detection, speed-to-lead SLA | Yes, and it would use existing canonical events only | 0 real replies, meetings or proposals exist to exercise it; pending replies already surface in `[PENDING REVIEW]` | **MINE_PATTERN**, not built (`revops_stage_hygiene_diagnostics: HYPOTHESIS`). Revival: the first real human reply |
| Lead scoring | non-compensatory gates (`prospect_eligibility_gate`, outreach score floor) | `revops`: points for fit and engagement, MQL at 50–80 of 100, calibrated on past wins | No | Points let engagement buy back a failed fit; there are 0 closed-won deals to calibrate against | **REJECT** |
| CRM automations and deal desk | HighLevel is the execution substrate (ADR-0001); ThePlus never rebuilds CRM | `revops`: lifecycle automations, routing, deal desk tiers | No | ADR-0001 | **REJECT** |
| Experiment design and reading | experiment contract, preregistration, single variable, review threshold, trust guardrails, maturity, delivered denominators, controlled-effect gate — mostly in code; `skills/experiment-design` 1.0.0 text was thin and still said "kill" | `ab-testing`: hypothesis, one variable, pre-committed sample, no peeking, guardrails, underpowered ≠ no difference; also ICE scoring, velocity targets, a winners playbook | Yes, in two places: the skill text lagged the engine, and nothing labelled an underpowered non-difference | Candidate comparison 1 below | **MINE_PATTERN** — built: `experiment-design` 1.1.0 and the evaluator's underpowered class |
| ICE prioritisation and experiment velocity | next experiment chosen by the funnel's measured constraint (`recommend_next_experiment`) | `ab-testing`: ICE 1–10 scores; experiments per month, win rate and backlog depth as leading indicators | No | Activity counts are not outcomes (Rule 0.9); the recommender already ranks by constraint | **REJECT** |
| Marketing context | registries (offers, campaigns and ICP, claims, evidence, buyer truth) and frozen experiment contracts, seeded in `seeds/registries.json` | `product-marketing`: one versioned context document with a changelog that every skill reads, auto-drafted from the codebase | Partly: no one-command context pack per marketing job | Auto-drafting from a codebase writes assumptions into context, against "customer evidence > AI-generated assumptions" | **REJECT** auto-drafting. **MINE_PATTERN**, not built, for version and changelog on a context pack (`marketing_job_context_packaging: HYPOTHESIS`). Revival: the first procedure A/B, where the pack's hash is frozen as a COMMON_INPUT |
| Procedure version lineage and A/B evaluation | none before this slice | none in any of the five: they neither version what an experiment ran nor say when a result may be called causal | Yes | — | **Built**: `procedures.py` |

## Candidate comparison 1 — `ab-testing` 2.0.0 vs `theplus.experiment-design` 1.0.0

**Evidence class:** OFFLINE_EVAL, structural. **Use case:** experiment_design.
- **Baseline:** `skills/experiment-design/SKILL.md` at 1.0.0, sha256 `25aa2fb46e0fd32c051e8cc77a6c9ee6f8c55ed6e7720a55eed86ce826e0cda5`.
- **Corpus:** ten decisions this repository already governs, each with the code that enforces it.
- **Scoring:** a procedure agrees only when its text states the governed decision, not when a reader could infer it.

| # | Governed decision | Enforced by | Baseline 1.0.0 | Candidate 2.0.0 |
|---|---|---|---|---|
| 1 | No verdict before the minimum sample | `registry.record_experiment_result` (PREREGISTERED below the sample) | MISS: requires a sample, never forbids a verdict below it | AGREE: a result below sample size is preliminary; don't peek |
| 2 | No verdict on exposures still inside the response window | `segments` / `change_diagnosis` maturity; `staged_verdict` NOT_READY | MISS | MISS: gives a duration, not a response window |
| 3 | The denominator is delivered exposure; bounces are attempts | `revenue_loop.undelivered_units` | MISS | MISS |
| 4 | One declared variable | `ExperimentSpec.validate` | MISS (in code, not in the skill text) | AGREE: test one thing |
| 5 | A guardrail breach sends a winner to review | `trust_verdict` in `record_experiment_result` | MISS: lists guardrails, states no rule | AGREE: stop if a guardrail is significantly negative |
| 6 | Below threshold goes to a person; it does not kill the business | `storage._rename_kill_to_review` | MISS: still says "kill threshold" | AGREE: a significant loser keeps control and asks why |
| 7 | Underpowered non-significance is not "no difference" | `change_diagnosis` INSUFFICIENT_DATA; now `procedures` underpowered | MISS | AGREE: no significant difference means more traffic or a bolder test |
| 8 | The decision rule is fixed before the result | preregistration | AGREE | AGREE: pre-determine sample size, commit to the methodology |
| 9 | A difference is attributable only within concurrent arms of one experiment, and does not transfer | `change_diagnosis._controlled`; `procedures.evaluate` | MISS | **CONTRADICTS**: promote winners to a playbook and apply them to other pages or flows |
| 10 | The primary metric is a buyer outcome, not activity | Rule 0.9; `procedures.ACTIVITY_METRICS` | MISS | **CONTRADICTS**: experiments launched per month, win rate and backlog depth as leading indicators of growth |

| Metric | Baseline 1.0.0 | Candidate 2.0.0 |
|---|---:|---:|
| Agreement with governed decisions | 1 / 10 | 6 / 10 |
| Missed guardrails | 9 | 2 |
| Unsupported recommendations | 0 | 2 (#9, #10) |
| False causal claims | 0 | 1 (#9) |

**Answers.**
- **What gap does it fix?** The baseline *skill text* lagged the engine: it omitted rules the code enforces and still said "kill".
- **What improved?** Five rules the candidate states, and the baseline text did not: #1, #4, #5, #6, #7.
- **What regressed?** Two candidate recommendations contradict governed decisions, and both cost money if followed:
  - applying a winner beyond the experiment that produced it;
  - counting experiment volume as growth.

  Its sample-size table (550 to 150,000 per variant) also assumes web traffic this business does not have.
- **Would we ADOPT, FORK or REJECT?** **REJECT** as a replacement; **MINE_PATTERN** for the five rules.
  - They were restated in ThePlus's own words, not copied, as `theplus.experiment-design@1.1.0` (sha256 `0a3d0fdfafb0291eaaa9cf1e910661e3e8bf276e596d8805aad2af1de7b14d5b`).
  - 1.1.0 was written from the engine's rules, so its agreement with this corpus holds by construction and is **not scored**.
  - The engine itself enforced 10 of 10 in code before this review.

**Limits:**
- One model reviewer, not an independent verifier.
- No experiment was run and no buyer was involved.
- Not market validation and not revenue evidence.

Result file: `docs/procedure-reviews/marketingskills-ab-testing-5b2c000.result.json`. It validates with
`age procedures validate-result`.

## Market comparison — real store

Run on 2026-09-15 against the local store:

```text
age marketing-engineer procedure --experiment-id EXP-ACQ-0003 --use-case message_generation
Result:   NOT_EVALUABLE — no procedure was declared for the candidate EXP-ACQ-0003 before exposure;
          a procedure's part in an outcome is never inferred from timing
Decision: NEED_MORE_DATA          (EXP-ACQ-0001: the same)

age procedures import <DISCOVERED agentvolt_demand_generation manifest reshaped as an export — synthetic>
REFUSED (not_approved): admission_status is 'DISCOVERED'; only an APPROVED export is consumed
```

Store counts before and after: funnel events 187, evidence 46, commercial evidence 0, outbound
lineage 27, reply candidates 12, experiments 3. No candidate has a market result.

## Next commercial experiment this enables

This review does not choose the next experiment; EXP-ACQ-0006's verdict on or after 2026-09-22 does.
When an outbound experiment is next designed, and only if the Intelligent Machine has admitted a
message-generation procedure by then:
- declare `variable = procedure`;
- bind `theplus.outreach-research@1.0.0` and the admitted version as VARIABLE arms before the first send;
- hold offer, ICP, channel and recipient route constant;
- evaluate on the preregistered qualified reply rate once 30+ matured deliveries per arm exist.

Until then, no external procedure touches a buyer.
