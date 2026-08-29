# GrowthOps Command Center functional and visual review — 2026-08-29

## Outcome

The initial industrial/editorial direction was rejected by the operator as looking novice. The
surface was rebuilt as a restrained professional operations console: persistent workspace
navigation, compact constraint and decision panels, a conventional KPI hierarchy, readable tables,
semantic status badges and progressively disclosed evidence. After the second operator review
correctly found it had no functionality, the surface gained a persistent human-gated outbound
workbench. It now progresses work rather than only describing it.

## Observed

| Check | 1440 × 1000 | 390 × 844 |
| --- | ---: | ---: |
| `scrollWidth` | 1440 | 390 |
| `clientWidth` | 1440 | 390 |
| Horizontal overflow | 0px | 0px |
| Constraint rendered | CONTACT FREEZE | CONTACT FREEZE |
| Product opportunities rendered | 5 | 5 |

- The visible state reported 51 qualified prospects, 50 delivered outreach, zero meaningful replies,
  zero customers and £0 collected revenue.
- Route integrity preserved `email/named_buyer` at 2/0 separately from `email/role_inbox` at 48/0.
- Eight recorded distribution channels rendered with their measured operating status.
- Eight commercial metrics, two experiments and eight evidence records rendered.
- The operator proposed one action and visibly required approval before execution.
- The authority boundary visibly reserved contact, publishing, spend and experiment changes for a
  human.
- Evidence statements collapse to concise summaries and can be expanded without navigation.
- The live-shaped workbench loaded 51 actionable prospects from `.age/growth.db`; disqualified rows
  did not appear.
- A full browser lifecycle ran against an isolated database: create sourced teardown/draft → approve
  → record operator-confirmed manual send → record meaningful reply.
- The isolated scoreboard changed to one delivered outreach and one meaningful reply, with route
  integrity showing `email/named_buyer` at 1/1. This was data produced by the UI workflow, not a
  fixture read directly from the store.
- Suppression is enforced both when creating a draft and immediately before recording a manual send.
- State-changing requests require `X-Command-Center-Intent: mutate`; ordinary cross-origin forms
  cannot supply it. JSON bodies are type-checked and capped at 64 KiB.
- The missing favicon request found during the first replacement render was fixed with an embedded
  icon. Final browser console warnings and errors: zero.
- HTTP regression tests prove reporting endpoints remain non-writable and assert `no-store`, CSP,
  referrer, content-type and frame-protection headers.

## Boundary

This is local internal verification, not public deployment or customer validation. The workbench
never sends externally. The browser test only recorded a send in an isolated temporary database;
no external action was executed and the real commercial store was not contaminated.
