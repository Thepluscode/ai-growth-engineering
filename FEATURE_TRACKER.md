# Digital Marketing Project — Feature and Market Tracker

Last updated: 2026-08-27

| Capability / outcome | Status | Evidence / next gate |
| --- | --- | --- |
| Project identity and scope | VERIFIED | Digital Marketing is the project; AI Growth Engineering is the method and engineering layer; `docs/ARCHITECTURE.md` defines the eight operating areas |
| Full-stack architecture of record | VERIFIED | `capability_map.json` declares 139 capabilities across all eight domains; semantic coverage tests prevent the source scope from silently collapsing back to the outbound wedge |
| Fourteen software-memory registries | DEPLOYED | The original ten plus social profiles, conversation funnels, audience ownership and value ladders have typed schemas, tested write/read interfaces and in-place migration support |
| Universal experiment contract | DEPLOYED | One persisted contract covers all 13 experiment namespaces, evidence lineage, controls, metrics, economics, samples, budgets, thresholds, dates, decisions and learning |
| Social conversion and attribution contract | DEPLOYED | Content, profile, DM, contact capture, offer, customer and revenue IDs share one lineage; deterministic tests cover funnel rates, audience capture, legacy schema migration and unknown denominators |
| Unit and lifecycle economics decision layer | DEPLOYED | Integer-pence models distinguish CAC from contribution profit and add realised 30/90/365-day value, gross profit per acquired customer and expansion rate; deterministic tests cover edge cases |
| Revenue-evidence OS `v0.1.0` | VERIFIED | Public [release](https://github.com/Thepluscode/ai-growth-engineering/releases/tag/v0.1.0) at commit `2af2070`; remote [test workflow](https://github.com/Thepluscode/ai-growth-engineering/actions/runs/32263253558) passed |
| `EXP-ACQ-0001` preregistration | VERIFIED | 50-send minimum; KEEP at >=10%, ITERATE at 5-9.9%, REVIEW below 5%; contract held to the end without amendment |
| `EXP-ACQ-0001` verdict | VERIFIED | `REVIEW` at n=50, observed 0.0, recorded 2026-08-27 by `age experiment-result`; written up in `experiments/EXP-ACQ-0001/VERDICT.md` |
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
| Qualified outbound sends | VERIFIED | 50 counted sends from 55 rows; `age import-outreach` then `age scoreboard` reports `outreach_sent 50/100`, five bounces excluded |
| Send recipient composition | VERIFIED | 48 of 50 went to a role inbox; 2 reached a named buyer's own address. The route actually tested was shared-inbox email, not buyer email |
| Queue-01 follow-up plan | DEPLOYED | Manual, value-adding first follow-ups prepared in `experiments/EXP-ACQ-0001/sales/follow-up-plan.md`; do not send before reply and suppression review on 2026-08-24 |
| Meaningful replies | VERIFIED | 0 of 50. Wilson 95% CI 0-7.1%; P(0 replies at a true 10%) = 0.52%, at a true 5% = 7.7%. Texaport's intake ticket remains automation, not a conversation |
| Named-buyer route | PLANNED | n=2, P(0 replies at a true 10%) = 81%. Untested, and must not be reported as failed |
| `recipient_class` on every send | VERIFIED | Required validated column; unknown values raise instead of defaulting; legacy rows report `unclassified` rather than joining a route. `age recipient-split` reports named_buyer 2/0 and role_inbox 48/0. Mutation-checked from a green baseline: `KILLED`, precise, file restored byte-identical |
| `EXP-ACQ-0002` preregistration | DEPLOYED | Named-buyer route only; 30-send minimum, same 10%/5% thresholds so the routes stay comparable; contract frozen in `experiments/EXP-ACQ-0002/PREREGISTRATION.md`; zero sends executed |
| `EXP-ACQ-0002` contact discovery | VERIFIED | **0 reachable named-buyer mailboxes across 18 observed accounts.** Wilson 95% CI 0-17.6%, ceiling ~10 of 55; 30 would need a 54.5% publication rate (P = 7e-7). Written up in `experiments/EXP-ACQ-0002/DISCOVERY-RESULT.md` |
| `EXP-ACQ-0002` execution | BLOCKED | Does not start. The contract stands unamended and unrun; it was not relaxed to fit the supply. Revival condition: 30 named-buyer addresses obtained without guessing |
| Email wedge for this ICP | VERIFIED CLOSED | Mid-market UK MSPs do not publish commercial decision-makers' addresses, so cold email is structurally a shared-inbox channel here — measured at 0/48. A property of the segment, not of the message |
| LinkedIn route feasibility | VERIFIED | Reachable but paid and not comparable. LinkedIn Help, first-party: free accounts get **5 personalised connection notes per month** — a 30-send minimum takes six months. Sales Navigator Core US$119.99/mo (50 InMail); Premium is likely the cheaper correct purchase. Written up in `experiments/EXP-ACQ-0003/FEASIBILITY.md` |
| LinkedIn route metric | VERIFIED | Not comparable to `EXP-ACQ-0001`: invite → accept → message → reply, and an unaccepted invite is a silent non-event, not a bounce. Thresholds must come from the invite-accept step, which has no baseline. The character-limited note also forces a message change, confounding channel with message |
| `EXP-ACQ-0003` | BLOCKED ON DECISION | Proposed, not preregistered. Needs a spend decision (subscription = money) before 30 profiles are researched or any invitation is sent |
| `outreach.channel` | VERIFIED | A LinkedIn send can no longer be counted in the email numbers. `age recipient-split` keys on `channel/recipient_class`; a row with no channel reports `unknown`, never `email`. Mutation-checked from a green baseline: `KILLED` precise on the grouping, sentinel fired on the channel default; both restored byte-identical |
| Discovery calls | PLANNED | 0; use `experiments/EXP-ACQ-0001/sales/discovery-checklist.md` |
| First proposal | PLANNED | Sell Diagnostic or Sprint only when discovery economics support it |
| First payment / customer dataset (`v0.2`) | PLANNED | No evidence yet |
| Commercial `v0.2` gate | IN PROGRESS | Architecture slice is implemented; commercial evidence is 50 counted sends, 0 meaningful replies, 0 discovery calls, 0 revenue. `age gate-check` reports REVENUE GATE: NOT MET |
| Owned-site baseline window | VERIFIED CLOSED | Closed early 2026-08-28. Read from Vercel's API, not the dashboard: **11 visitors / 14 pageviews in the clean 7-day window** (~1.6/day, ~47/month). All 35 all-time visitors have an empty referrer — no channel is pointing at the site |
| `EV-BASELINE-01` | WITHDRAWN | "47 sessions, 3 events, 6.4%" cannot be reproduced. Cumulative as of 2026-08-21 was 24 visitors / 36 pageviews; no day reached 47 of anything, and it is not an environment-filter artefact. The conclusion drawn from it was wrong by ~30x and overturned a correct prediction |
| Conversion numerator | BLOCKED | `contact_intent` is a custom event; `events/count` returns **402 — requires Pro or Enterprise** and the team is on `hobby`. The numerator is unreadable now and in future without an upgrade |
| `EXP-CREATIVE-0001` | NOT RUNNABLE | Constraint is audience, not creative. At 11 visitors/week the most generous power cell (870 sessions, 5%→10%) takes **1.5 years**; 1%→1.5% takes 27 years. Nothing preregistered |
| Distribution | VERIFIED CONSTRAINT | Three independent measurements agree: shared-inbox email 0/48, personal email route unreachable, owned site ~47 visitors/month with zero referrers. Nothing in creative, offer or messaging has been falsified — none of it has been given a sample |

## Current experiment freeze

No product features are authorised by `EXP-ACQ-0001`. Work on this experiment is limited to prospect
qualification, teardown research, manual outreach, discovery, proposals, and evidence capture until
its market gate passes. This does not redefine the Digital Marketing Project as an outbound or
cybersecurity project.
