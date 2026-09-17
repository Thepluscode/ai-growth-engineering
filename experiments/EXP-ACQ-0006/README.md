# EXP-ACQ-0006 — FS-001 field-service wedge (imported, live)

> **HISTORICAL** — narrative as written on 2026-09-15, kept unedited. Live counts are generated in `docs/STATE.json`.

**Imported:** 2026-09-15 from the separate `~/projects/ai-growth-engineering` repository, where it
ran as `FS-001` / `EXP-0004`. **Status: LIVE — outcome window open until 2026-09-22.** No verdict
before then.

The full state (frozen cohort, send pack, routing attempts, queue) is preserved locally at
`imports/marketing-engineering-os/` (git-ignored: personal data, public repository). No person
or company is named here.

## Hypothesis

UK field-service operators (HVAC, plumbing, electrical; 5–50 technicians) lose revenue and staff
time because their scheduling software does not encode their operating rules. At least one will
pay GBP 1,500–3,000 for a scoped sprint that automates one dispatch workflow **without replacing**
that software. A founder-conviction bet; nothing in the evidence base touched this vertical.

## State at import

| | |
|---|---|
| Researched | 46 companies, 8 not eligible; cohort frozen 2026-09-08 at 30 |
| Stage A (routing: who owns the engineer diary) | **22 sent on 2026-09-08**, 1 hard bounce, **21 awaiting an outcome** |
| Demand | not asked yet — Stage A offers nothing and asks no meeting |
| Caveat | all 22 delivered messages were reworded after the gate-approved draft, so the batch measures an unscreened message; each attempt is flagged |

## Recording outcomes until 2026-09-22

Run from the preserved copy, which has its own virtual environment:

```bash
cd imports/marketing-engineering-os
.venv/bin/theplus-growth fs001-outcome FSP-0023 routed_to_buyer --note "put me through to Dawn"
.venv/bin/theplus-growth fs001        # funnel against the preregistered gates
```

Outcomes: `routed_to_buyer` · `route_refused` · `no_response` · `wrong_organisation` ·
`gatekeeper_blocked` · `undeliverable`. The judge-not-before date is enforced in code.
