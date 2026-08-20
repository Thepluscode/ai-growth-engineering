# Working agreement for agents in this repository

Applies to every agent and every session — Claude Code, Codex CLI, or anything else.

## Commit to `main` directly

Do not create `codex/*`, `agent/*` or other working branches here. Commit to `main`
and push.

This is not a style preference. It has already cost real time twice on 2026-08-20:

1. **In the website repo**, production was deploying from `codex/autopsy-preview`
   while `main` held an abandoned Vite scaffold from May. An agent asked to add
   analytics cloned the default branch, instrumented it, tested it, and pushed —
   all of it aimed at an application nobody was serving. The Vercel project was
   even *named* after the repo, which made the wrong answer look right.

2. **In this repo**, fourteen commits accumulated on `codex/batch-02-market-evidence`
   while `main` sat behind. `git push origin main` then reported
   **"Everything up-to-date"** and exited 0, because the local `main` genuinely was
   up to date — the work was on another branch. A push that pushed nothing,
   reporting success.

Both failures share a shape: `main` stops being the truth, and every tool and
person that assumes otherwise gets a stale answer with no error to warn them.

A `pre-commit` hook enforces this. It lives in `.githooks/` rather than
`.git/hooks/` so it survives a clone — a hook that vanishes on clone is the same
invisible absence it exists to prevent. Enable it once per checkout:

```bash
make hooks
```

If a branch is genuinely warranted — a risky migration, work needing review before
it lands — say so out loud and merge it the same session:

```bash
ALLOW_BRANCH_COMMIT=1 git commit ...
```

The override is an environment variable rather than `--no-verify` so that
bypassing is deliberate, visible in the shell history, and greppable. Rebase,
merge, cherry-pick and bisect are unaffected; blocking those would break ordinary
history repair.

## Verify a push by reading the remote

`git push` printing "Everything up-to-date" is not proof your commits are on the
remote. Confirm with the remote itself:

```bash
git ls-remote origin refs/heads/main   # must equal `git rev-parse HEAD`
```

The same rule applies to every green check in this repo: read what the command
printed and what the remote actually holds, never infer success from exit status.

## Registry rows go in `seeds/registries.json`

The store under `.age/` is gitignored and rebuildable. Rows inserted ad hoc live
only there, and `make demo` destroys them — which has already happened once,
taking eight channels, four offers, ten claims and nine evidence rows with it.

Anything worth keeping is added to `seeds/registries.json` and loaded by
`age seed-registries`, which runs as part of `make demo` and is idempotent.

## Before claiming anything is done

`make test` runs the tests, the scope gate and the tree gate. All three must pass.

- The engine (`src/`, `skills/`, `policies/`, `templates/`, `tests/`) stays
  market-neutral; market-specific work belongs under `experiments/<EXP-ID>/`.
- `capability_map.json` is the architecture of record. A directory is not a claim
  that anything is built; the map's status is.
- No experiment verdict before its minimum sample. `REVIEW` means "below the line,
  come and look" — the system does not pronounce on the business.
