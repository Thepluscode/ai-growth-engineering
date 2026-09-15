# EXP-ACQ-0005 — CTA size on named buyers (imported)

**Imported:** 2026-09-15 from the separate `~/projects/ai-growth-engineering` repository, where it
ran as `EXP-0003`. **Status: HELD** — `EXP-ACQ-0003` goes to market first (founder, 2026-09-15).
**Nothing has been sent.** The Apollo lookup for the top-up is approved but has not been run.

## Why it is here

A session on 2026-09-03 started a separate repository instead of working in this one, and the
work continued there. The founder moved everything back on 2026-09-15. The full source
repository — history, audit log, cohort files, Apollo inputs and outputs — is preserved
locally at `imports/marketing-engineering-os/` (git-ignored: it holds names and business email
addresses, and this repository is public). This README is the public record; no person is
named in it.

## Hypothesis and arms

A one-word reply ask produces a higher qualified reply rate than a meeting ask when both go to
named buyers. The only variable is the final CTA.

| Arm | CTA (verbatim) |
|---|---|
| control | Would you be open to a 20-minute working session on one workflow? |
| variant | Want me to run the first pass on one workflow? Reply 'teardown'. |

- **ICP:** B2B companies with AI agents or autonomous AI workflows in production, 20–500 staff.
  This is a different market from `EXP-ACQ-0001`–`0003` (UK cybersecurity consultancies and MSPs).
- **Primary metric:** qualified reply rate. **Minimum sample preregistered:** 29 per arm.

## State at import

| | |
|---|---|
| Eligibility cohort (V2) | 58 participants (29 / 29) + 32 ordered reserves, fingerprint `e81887ca…`, approved for email lookup only |
| Apollo rounds 1–2 | 90 identities looked up; **32 message-ready: control 14, variant 18**; all reserves used |
| Off-domain addresses | 5, **kept blocked** unless an address is shown to be an official business address (founder) |
| Top-up block TOPUP-002 | 371 companies researched to exhaustion → **65 eligible (control 41, variant 24)**, frozen before any email lookup, fingerprint `e52d9027…` |
| Apollo credits | up to **65** approved as a hard ceiling (audit `AUD-00179`); **lookup not run** |
| Expected after the lookup | about 13 control / 10 variant verified, so roughly 27 / 28 per arm |
| Prior contact | 0 overlap between this experiment's 155 domains and this repository's `growth.db` and files (checked 2026-09-15, with a positive control) |

## Decisions already taken by the founder

- No further top-up to force 29/29. Freeze the actual round-1 roster, run it, report it as
  **descriptive** and always show the denominators.
- One subject, one body, one sender, one personalisation standard; only the CTA differs.

## Message base copy (approved 2026-09-14)

Subject: `{Company}'s agents in production`

```
Hi {first_name},

{opening_line}

Once agents are live in production, buyers can ask a harder question: can you show what the agent did, why it did it, and who approved it?

I'm testing a review-only pass on one production agent workflow: where that evidence exists, where it is missing, and where a buyer review could stall. No system access needed.

{CTA}

Theophilus Ogieva
ThePlus Tech
```

`{opening_line}`: one sentence, one verified public fact from the buyer's frozen trigger, no
praise, no guessed pain — written in one pass over the final roster with arms hidden.

## To resume (only on the founder's word)

Apollo lookup of the 65 TOPUP-002 identities → import → actual arm denominators → arm-blind
opening lines → freeze the rendered pack → final suppression and prior-contact check (both
repositories) → explicit SEND approval → send → 14-day outcome window.

> **ID note:** `EXP-ACQ-0004` is reserved by `EXP-ACQ-0003/PREREGISTRATION.md` for the paid personalised-note PIVOT branch, so this import takes `EXP-ACQ-0005`.
