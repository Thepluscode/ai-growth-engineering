# Session-start continuity enforcement — design

Status: **DESIGN** (2026-09-26). Nothing here is installed. Installation into
`~/.claude/settings.json` is a separate founder decision.

## Problem

`~/.claude/scripts/preflight` proves where a session is and what it may do, but only when
someone runs it. The continuity contract is therefore prose until it runs by itself.

## Constraint that shapes everything

Checked against the Claude Code hooks reference (`code.claude.com/docs/en/hooks`, read
2026-09-26):

- **SessionStart cannot block.** Exit 2 "shows stderr to user only"; the session proceeds.
  Its plain-text stdout / `additionalContext` *is* added to Claude's context.
- **CwdChanged cannot block** either, and fires only on shell `cd`.
- **PreToolUse can block**, per call: exit 2, or
  `hookSpecificOutput.permissionDecision: "deny"` with a reason Claude sees.

So "enforcement" cannot mean refusing to start. It means: tell the session at start,
and refuse mutating tool calls while the checkout is in a state that must stop work.

## Design

Two hooks, one shared decision function. Preflight stays the only implementation of the
contract; the hooks call it and never re-derive it.

### 1. SessionStart — inform (all repositories)

Run `preflight "$cwd"` and emit its report as context. Never exit 2 (it would only show a
notice the model cannot see). Runs on `startup`, `resume`, `clear`, `compact`, so a
resumed session gets fresh state rather than a replayed stale report.

### 2. PreToolUse — enforce (mutations only)

Matcher: `Edit|Write|NotebookEdit|Bash`. (The existing premise-gate matcher is
`Write|Bash` and so never sees `Edit` — do not copy it.)

Target directory: `tool_input.file_path`'s parent for file tools; `cwd` for Bash.
A file edit is judged by *where the file is*, not where the session started — an edit into
the deviated AGE copy from a canonical session must still be caught.

| preflight result | migrated repo | unmigrated repo |
|---|---|---|
| exit 2 `WRONG_REPO` | **deny** | **deny** |
| `BRANCH_BEHIND_CONTINUITY` | **deny** | n/a |
| `STATE_*` (exit 3) | allow, reason appended | allow |
| `active` missing / unreadable | **deny**, except edits to `ACTIVE_WORK.yaml` itself | allow |
| exit 0 | allow | allow |
| preflight crashed / timed out | allow + stderr notice | allow |

**Migrated** = preflight's own `continuity_status`: `AGENT_CONTEXT.md` and
`ACTIVE_WORK.yaml` on the branch. No second definition.

Known gap: a Bash command that `cd`s into another tree inside the command string
(`cd ~/projects/ai-growth-engineering && …`) is judged by the session `cwd`, not by the
tree it mutates. Accepted: parsing shell to find the real target is the parser this design
refuses to write. The file tools, which carry an explicit path, are fully covered.

Read-only Bash is not exempted by parsing the command — command classification is a
parser the hook would get wrong. Deny rules above are narrow enough that a blocked session
has nothing legitimate to do in that tree anyway.

### Why STATE_* never denies

Committing `docs/STATE.json` makes it describe the parent of the commit that contains it,
so every healthy checkout reads `STATE_HEAD_MISMATCH` (exit 3) immediately after any
commit. Observed 2026-09-26 at `afafabc`. Denying on exit 3 would block every session after
every commit — the denial of service the parking lot warned about. Staleness is a fact
about *numbers*, so it is surfaced where numbers are read, not enforced on edits.

### Exit-code contract

Unchanged: `0` ok · `2` wrong tree · `3` actionable (stale state, missing task, branch
behind). The hook maps these through the table; preflight gains no hook-specific codes.

### Bypass

`THEPLUS_CONTINUITY_GATE=off` in the launching environment disables the PreToolUse deny
(SessionStart still reports). Every bypassed decision that *would* have denied is appended
to `~/.claude/logs/continuity-gate.jsonl` with cwd, tool, status and time — a bypass that
leaves no record is indistinguishable from a gate that never fired.

### What a denied session sees

The deny reason is preflight's STOP block verbatim plus one line naming the canonical path
or the command that clears it. Nothing else — the model acts on the reason it is given.

### Fail-open vs fail-closed

The hook fails **open** on its own errors (crash, timeout > 5 s, unparseable input), with a
stderr notice. It fails **closed** only on a positive result from preflight. A gate that
blocks real work because the gate is broken teaches everyone to set the bypass.

## Retiring advisory mode

Advisory ("allow" in the unmigrated column) exists only because unmigrated repositories
cannot be judged against a contract they do not have. It retires per repository, not by a
flag day: the moment a repo carries the contract, preflight classifies it MIGRATED and the
migrated column applies automatically. When `portfolio_continuity_rollout` reports no
UNMIGRATED active repositories, the unmigrated column's `active missing` row flips to
deny and the column is deleted.

As of 2026-09-26, 14 repositories under `~/projects` carry both contract files.

## Verification required before installation

1. A test per deny row, with its positive twin (the allowed case in the same tree).
2. Mutation: break the deny branch, watch the deny tests go red.
3. Edit into `~/projects/ai-growth-engineering/` from a canonical session → denied.
4. A commit followed by an edit in AGE → allowed (the HEAD_MISMATCH case).
5. Latency measured per call; preflight alone is ~0.15 s on AGE.

## Open item this surfaced

The closed task's criterion "preflight exits 0 on a healthy canonical checkout" holds only
between `make snapshot` and the next commit. Candidate fix, not in this design's scope:
treat `STATE_HEAD_MISMATCH` as OK when the only files changed between the described commit
and HEAD are the state file and authority files that do not feed the snapshot.
