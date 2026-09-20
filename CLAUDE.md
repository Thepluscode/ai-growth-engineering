# Start here

A fresh session reconstructs this project from the repository, never from memory or
from the previous conversation. Six steps, in order.

1. **Verify you are in the canonical repository.**
   `~/projects/ai/ai-growth-engineering`. Not `~/projects/ai-growth-engineering`
   (deviated, moved 2026-09-15), not `imports/` (a preserved copy).

2. **Read `AGENT_CONTEXT.md`** — mission, product, boundaries, invariants. Stable.

3. **Read `ACTIVE_WORK.yaml`** — the authoritative current task, what is blocked,
   what is parked, and the dated gates. This file decides what you work on.

4. **Run preflight.** `~/.claude/scripts/preflight .` — exits non-zero rather than
   warning.

5. **Refresh generated state.** `make snapshot` writes `docs/STATE.json`. Every
   count, SHA and experiment figure comes from there or from the store, never
   from memory.

6. **Act only on the task `ACTIVE_WORK.yaml` names.**

Nothing else belongs in this file. Project doctrine lives in `AGENT_CONTEXT.md`;
duplicating it here is how the two drift apart.

## The one rule this file exists to enforce

The most recently discussed defect, buyer, feature or idea does **not** become the
current task. Discovery is not authorisation. Park it, and carry on with what
`ACTIVE_WORK.yaml` says.

Changing the active task requires `FOUNDER_OVERRIDE`, `CURRENT_TASK_COMPLETED`,
`RELEASE_CONDITION_MET`, or a verified `P0`/`P1` interrupt — and the switch records
its reason. See `~/.claude/rules/rule-precedence.md` §B.
