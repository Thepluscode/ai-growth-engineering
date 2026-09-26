# Parking lot

Things worth doing that are **not** current work. An entry here is a decision to wait, not
a queue position — promotion needs `ACTIVE_WORK.yaml` to change, under one of its named
conditions.

Keep this bounded. A parking lot that becomes a roadmap dump stops being read, and an
unread list is the same as no list.

---

## Committed state reads as stale after every commit

**Status:** `FOUND 2026-09-26` · not scheduled

A committed `docs/STATE.json` describes the parent of the commit containing it, so
preflight reports `STATE_HEAD_MISMATCH` (exit 3) on a healthy checkout right after any
commit. The closed continuity task's "exits 0 on a healthy checkout" holds only between
`make snapshot` and the next commit. Candidate fix and its constraint are in
`docs/SESSIONSTART_HOOK_DESIGN.md` → "Open item".

---

## Portfolio continuity rollout

**Status:** `NOT_ACTIVE`

Order established by audit: EdgeForge · TrustLedger_v2 · CyberGuardPlus · Control Plane ·
Intelligent Machine · Mandate · ACN · SIBM · website · knowledge repo.

**Why it waits:** AGE proves the pattern first. Rolling an unproven contract across
thirty-nine repositories multiplies whatever is wrong with it.

---

## Orphaned project memory trees

**Status:** `NOT_ACTIVE` · nothing deleted

Thirteen memory trees describe directories that no longer exist, including the deviated
AGE repo's six files. They are unreachable by any session and may hold directives never
migrated.

**Before archiving:** read them for durable doctrine, migrate only what is genuinely
missing, never migrate stale queryable state, then archive with a manifest.
