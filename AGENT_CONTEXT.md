# AGENT_CONTEXT — the Digital Marketing Project

Stable truth only. Nothing here changes week to week. **No counts, no SHAs, no test
totals, no experiment outcomes** — those are generated into `docs/STATE.json` and read
from the store. A number written here is a claim about the past wearing the present
tense.

## Mission

> Build and operate measurable digital marketing systems that acquire customers,
> increase conversion and grow revenue.

## Product

**ThePlus Marketing Engineer.**

## Method

**Digital Marketing is the domain. AI Growth Engineering is the methodology** — an
evidence-driven, experimental engineering layer for researching markets, creating and
distributing marketing, measuring acquisition economics, and improving revenue outcomes.

## What this project is not

It is not defined by, and must never be reduced to:

- one experiment · one buyer · one market
- cybersecurity consultancies or MSPs
- LinkedIn · Gmail · outbound email
- one offer · one campaign · one named account

**Experiments feed the Marketing Engineer; they do not define it.** The current
experiments are Customer Zero evidence for ThePlus-Tech. A finding inside one of them is
an observation about that experiment, not a redefinition of the project.

## The closed loop

```
Market Evidence → Customer Truth → Opportunity → ICP → Offer
→ Campaign / Creative / Channel → Experiment → Exposure → Response
→ Qualified Conversation → Meeting → Proposal → Customer → Revenue
→ Learning → Better Next Decision
```

The Marketing Engineer exists to answer: which market · who to target · which problem has
evidence · which offer · what message · which route · where the funnel leaks · what
produces customers and revenue · why performance changed · what to test next.

## Operating areas

Eight, as `docs/ARCHITECTURE.md` defines them: market intelligence · strategy · creative ·
distribution · conversion · lifecycle and revenue · measurement and economics · AI growth
engineering.

`capability_map.json` is the architecture of record. A directory is not a claim that
anything is built; the map's status is. It is a roadmap, **not permission to build without
commercial priority** — `ACTIVE_WORK.yaml` decides what is built.

## Source-of-truth rules

Authority for facts, highest first — the full order is `~/.claude/rules/rule-precedence.md` §B:

1. founder instruction → 2. this file and `CLAUDE.md` → 3. `ACTIVE_WORK.yaml`
→ 4. the store and `docs/STATE.json` → 5. code and tests → 6. Git → 7. decisions
→ 8. Claude memory → 9. recent conversation

**Claude memory is never authoritative** for counts, SHAs, test totals, current
experiment state, or the current task. Re-query. Where memory and the store disagree, the
store wins and the memory is stale.

**Raw event counts are not effective counts.** `funnel_events` holds corrections; an event
superseded by one must not be counted. Reading `GROUP BY event_type` without applying
`corrects_event_id` has already produced wrong figures in a report.

## Invariants

- **Commit to `main` directly.** No `codex/*` or `agent/*` branches. A `pre-commit` hook in
  `.githooks/` enforces it; `make hooks` enables it per checkout. Override deliberately
  with `ALLOW_BRANCH_COMMIT=1`.
- **Verify a push by reading the remote.** `git ls-remote origin refs/heads/main` must
  equal `git rev-parse HEAD`. "Everything up-to-date" has reported success while pushing
  nothing.
- **Registry rows go in `seeds/registries.json`.** The store under `.age/` is gitignored
  and rebuildable; `make demo` destroys ad-hoc rows, and has.
- **The engine stays market-neutral.** `src/`, `skills/`, `policies/`, `templates/`,
  `tests/` carry no market-specific vocabulary; that belongs under `experiments/<EXP-ID>/`.
  `scripts/scope_gate.py` enforces it.
- **No experiment verdict before its minimum sample.** `REVIEW` means "below the line,
  come and look" — the system does not pronounce on the business.
- **External action is human-gated.** Contact, spend and publish require approval. The
  system may observe, rank and draft; it may not send.
- **No natural-person data in this public repository.** `scripts/pii_guard.py` enforces it.

## Before claiming anything is done

`make test` runs the suite, the scope gate, the tree gate, the PII guard and docs_check.
All must pass. A guard never observed failing is decoration: break it and watch it go red.
