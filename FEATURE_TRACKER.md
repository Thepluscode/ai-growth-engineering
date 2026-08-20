# Digital Marketing Project — Feature and Market Tracker

Last updated: 2026-08-19

| Capability / outcome | Status | Evidence / next gate |
| --- | --- | --- |
| Project identity and scope | VERIFIED | Digital Marketing is the project; AI Growth Engineering is the method and engineering layer; `docs/ARCHITECTURE.md` defines the eight operating areas |
| Full-stack architecture of record | VERIFIED | `capability_map.json` declares 139 capabilities across all eight domains; semantic coverage tests prevent the source scope from silently collapsing back to the outbound wedge |
| Fourteen software-memory registries | DEPLOYED | The original ten plus social profiles, conversation funnels, audience ownership and value ladders have typed schemas, tested write/read interfaces and in-place migration support |
| Universal experiment contract | DEPLOYED | One persisted contract covers all 13 experiment namespaces, evidence lineage, controls, metrics, economics, samples, budgets, thresholds, dates, decisions and learning |
| Social conversion and attribution contract | DEPLOYED | Content, profile, DM, contact capture, offer, customer and revenue IDs share one lineage; deterministic tests cover funnel rates, audience capture, legacy schema migration and unknown denominators |
| Unit and lifecycle economics decision layer | DEPLOYED | Integer-pence models distinguish CAC from contribution profit and add realised 30/90/365-day value, gross profit per acquired customer and expansion rate; deterministic tests cover edge cases |
| Revenue-evidence OS `v0.1.0` | VERIFIED | Public [release](https://github.com/Thepluscode/ai-growth-engineering/releases/tag/v0.1.0) at commit `2af2070`; remote [test workflow](https://github.com/Thepluscode/ai-growth-engineering/actions/runs/32263253558) passed |
| `EXP-ACQ-0001` preregistration | DEPLOYED | 50-send minimum; KEEP at >=10%, ITERATE at 5-9.9%, REVIEW below 5% |
| 50 qualified prospects | VERIFIED | 57 records: seven are explicitly disqualified; Batches 04 and 05 add 20 current UK accounts; CLI reports 50 and the reseed regression test prevents stale qualification statuses from inflating the count |
| Queue-01 deep research | VERIFIED | 10 queue accounts researched from cited public sources; Foresite disqualified; Morcan researched as send replacement |
| Queue-01 teardowns | VERIFIED | 10 queue decisions plus Morcan replacement under `experiments/EXP-ACQ-0001/sales/teardowns/`; observed/inferred/unknown separated |
| Queue-01 messages | VERIFIED | 10 qualified messages sent through Gmail on 2026-08-19; full copy in `experiments/EXP-ACQ-0001/sales/outbound-messages.md` |
| Queue-02 qualification | VERIFIED | 10 next-batch accounts qualified in `experiments/EXP-ACQ-0001/sales/batch-02-qualification.md`; RSK and Stingrai disqualified during qualification, then standalone QuoStar was replaced by current owner Zenzero after its live redirect was observed |
| Queue-02 teardowns | VERIFIED | 10 evidence-backed teardowns in `experiments/EXP-ACQ-0001/sales/teardowns/12-cyberisms.md` through `21-chorus.md`; every file passes the ten-section contract and separates observation from inference |
| Queue-02 messages | IN PROGRESS | 9 of 10 messages confirmed SENT; Slink remains unsent because its live site exposes only a contact form and browser submission requires action-time confirmation |
| Queue-03 qualification | VERIFIED | 10 current accounts qualified; Bulletproof and Bridewell disqualified during verification and replaced with clean wedge fits |
| Queue-03 teardowns | VERIFIED | 10 evidence-backed teardowns in `experiments/EXP-ACQ-0001/sales/teardowns/22-air-it.md` through `31-mitigo.md`; 100 required sections validated |
| Queue-03 messages | DEPLOYED | 10 personalised OBSERVATION + ECONOMIC HYPOTHESIS + LOW-FRICTION CTA messages staged and verified as Gmail drafts; none counted as sent |
| Queue-04 qualification and teardowns | VERIFIED | 10 current accounts qualified and 10 evidence-backed teardowns completed; all 100 required sections and inference labels validated |
| Queue-04 messages | DEPLOYED | 10 personalised messages staged and verified as Gmail drafts after duplicate and suppression checks; none counted as sent |
| Queue-05 qualification and teardowns | VERIFIED | 10 current accounts qualified; Six Degrees disqualified as an enterprise-scale outlier and replaced with Inology; all 100 required teardown sections and inference labels validated |
| Queue-05 messages | DEPLOYED | 10 personalised messages staged and verified as Gmail drafts after duplicate and suppression checks; none counted as sent |
| Qualified outbound sends | IN PROGRESS | 19 total confirmed sends; sends 20–50 are mapped one-to-one in `sales/execution-manifest-50.csv`; no message or form submission is counted without evidence |
| Queue-01 follow-up plan | DEPLOYED | Manual, value-adding first follow-ups prepared in `experiments/EXP-ACQ-0001/sales/follow-up-plan.md`; do not send before reply and suppression review on 2026-08-24 |
| Meaningful replies | PLANNED | 0; 2026-08-19 inbox audit found no buyer reply; Texaport's intake ticket remains automation, not a conversation; no conclusion before 50 qualified sends |
| Discovery calls | PLANNED | 0; use `experiments/EXP-ACQ-0001/sales/discovery-checklist.md` |
| First proposal | PLANNED | Sell Diagnostic or Sprint only when discovery economics support it |
| First payment / customer dataset (`v0.2`) | PLANNED | No evidence yet |
| Commercial `v0.2` gate | IN PROGRESS | Architecture slice is implemented; commercial evidence is 19 confirmed sends, 0 meaningful replies and 0 discovery calls; 31 additional routes are staged but not counted; no conclusion before 50 confirmed qualified sends |

## Current experiment freeze

No product features are authorised by `EXP-ACQ-0001`. Work on this experiment is limited to prospect
qualification, teardown research, manual outreach, discovery, proposals, and evidence capture until
its market gate passes. This does not redefine the Digital Marketing Project as an outbound or
cybersecurity project.
