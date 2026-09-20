# Parking lot

Things worth doing that are **not** current work. An entry here is a decision to wait, not
a queue position — promotion needs `ACTIVE_WORK.yaml` to change, under one of its named
conditions.

Keep this bounded. A parking lot that becomes a roadmap dump stops being read, and an
unread list is the same as no list.

---

## Market Hypothesis & Cross-Market Evidence Layer

**Status:** `DESIGN_READY` · parked behind the continuity reference implementation

Markets become first-class objects with evidenced fields only, experiments reference a
market, and evidence is held in five independent layers — `RESEARCH` · `ACCESS` · `DEMAND`
· `COMMERCIAL` · `PAID` — which are never inferred from one another. A market with tested
access and untested demand reads as exactly that.

The design already recovered four market hypotheses from frozen documentation, and the
correct first output of a comparison is `NOT_ENOUGH_EVIDENCE`.

**Why it matters:** the project can rank prospects inside a market and cannot compare one
market to another, so after a run of exposures it cannot say whether the message or the
market is wrong.

**Do not, when it starts:** pool non-comparable experiments into one denominator. Stage A
routing attempts are access evidence, not demand exposures, by their own preregistration.

---

## SessionStart enforcement hook

**Status:** `PARKED_UNTIL_REFERENCE_IMPLEMENTATION`

Preflight is manual. Wiring it to session start would make the continuity contract
structural rather than prose.

**Why it waits:** no repository has `ACTIVE_WORK.yaml` yet, and most generated state
cannot prove its age. Fail-closing today would block legitimate work across every
unmigrated repository — a safeguard turned into a denial of service.

**Shape when it lands:** migrated repository → enforcement; unmigrated → advisory.
Advisory mode disappears when migration completes.

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
