# EXP-ACQ-0007 — message-generation review sample

**2026-09-16 · nothing sent, queued or scheduled. `OUTREACH_SENT = 0`.**

Three cohort accounts, six messages: each account written twice, once by each arm's procedure,
from the **same observed evidence, the same offer and the same evidence constraints**. The only
intended difference is the procedure. No person is named in this file; the full paired text,
which quotes named officers, stays in the local working copy.

| | Account A | Account B | Account C |
|---|---|---|---|
| Register | `07550944` | `07019261` | `09809709` |
| Domain | dialageek.co.uk | managed.co.uk | digitalxraid.com |
| Shared evidence | CE, ISO 27001, IASME, B Corp, 13 case studies, published pricing, 5 locations, 24/7 MDR | ISO 27001, ISO 9001, ISO/IEC 20000-1, CE Plus, 24/7/365 desk, 4 offices, 10 sectors, NPS 94.1 | CE, ISO 27001, CREST, CHECK, Microsoft Partner, 24/7 SOC, 16 case studies, 14+ sectors |

The candidate procedure ran against the package verified at
`content_sha256 5736b9db…` / `package_sha256 bb06fb96…`, recomputed with the Intelligent Machine's
own `quarantine()` and matching the approved manifest exactly.

## Scores — AGE's own scorer, AGE's own thresholds

`OutreachQuality` (`scoring.py`): six components 0–5; <18 DO_NOT_SEND, 18–23 REVIEW, 24+ SEND. The
component values are a human assessment against that rubric; the arithmetic and the decision bands
are the repository's.

| Message | Total | Decision | research_evidence | cta_friction |
|---|---|---|---|---|
| A control | 26 | SEND | 5 | 3 |
| A treatment | 26 | SEND | 3 | 5 |
| B control | 28 | SEND | 5 | 3 |
| B treatment | 27 | SEND | 3 | 5 |
| C control | 27 | SEND | 5 | 3 |
| C treatment | 26 | SEND | 3 | 5 |

Control mean **27.00** (26–28) · treatment mean **26.33** (26–27). Every message clears 24; none
lands in the review band and none is below the send floor, so **no score-threshold bypass** occurs
in either arm.

The totals are nearly identical and the composition is not. The treatment trades **evidence
(5 → 3) for lower-friction asks (3 → 5)** in all three pairs. That trade is the finding, and it is
invisible in the total.

## Contamination checks

| Check | Control | Treatment |
|---|---|---|
| Unsupported inference asserted about the prospect | 0 of 3 | **2 instances, in 1 of 3** |
| Source citation for the observed signal | 3 of 3 | **0 of 3** |
| Unverified market generalisation ("most providers…") | 4 instances | 3 instances |
| Follow-up sequencing | none | none |
| Bulk or volume guidance | none | none |
| Autonomous sending | none | none |
| Policy bypass | none | none |
| Score-threshold bypass | none | none |
| Evidence unavailable to the other arm | none | none |

### What the treatment actually did differently

1. **It dropped the citation.** Every control message carries the source and the observation date
   inline (`domain, observed 16 Sep 2026`); no treatment message does. The control procedure
   forbids asserting a signal "that was not observed on a named source" and requires every claim
   to trace to one. The candidate's guidance optimises for brevity and peer voice and says nothing
   about provenance, so the citation is the first thing its rules spend.
2. **It asserted the prospect's situation twice, on one account.** "the AI question is already
   arriving from your clients" and "there is no register of what your own tools decided" state
   unobserved facts about that company. Its own `personalization.md` pushes this way: Level 4 is
   defined as a specific observation about the person, and the "So what?" test rewards a concrete
   claim over a hedged one.
3. **Market generalisations are not a treatment defect.** Both arms make them, the control slightly
   more often. Anyone reading only the treatment's output would misattribute this.

Nothing in the sample exercised the parts of the skill outside its approved scope. The package
does contain `references/follow-up-sequences.md`, which is exactly the sequencing the approval
excludes — it was not used, and the approval scope, not the skill's contents, is what binds.

## Gate results

- `GrowthActionPolicy` on "generate a draft for review, no send": **allowed, no approval required**,
  reason `within_default_authority`. Generating a draft is inside default authority; sending is not,
  and nothing here sends.
- **Suppression check is vacuous and is not evidence.** None of the three accounts appears in the
  suppression table — and the table holds **0 rows**, so the query would return "not suppressed"
  for any input, including a suppressed one. It is recorded as a check that has not yet been given
  the chance to fail. Before any send, this needs a positive control: a known-suppressed identity
  that the same query refuses.

## Reading for the decision this sample exists to inform

The candidate does not obviously write worse messages — it writes shorter ones with easier asks and
a thinner evidential base. On this repository's standards that is a real risk, because the control's
evidence discipline is a governance property and not a stylistic preference: a message whose claim
cannot be traced to a named source is the failure the outreach procedure was written to prevent.

If the experiment runs as preregistered, the honest reading of a candidate win would be that lower
friction beat evidence density on reply rate — not that the candidate writes better messages. That
distinction should be settled before the first send, not after the result.

**Recommended before message generation proper:** require the candidate arm to carry the same
source citation the control does, as a constant held across both arms rather than as a procedure
difference. That keeps the single variable clean and removes the one contamination this sample
actually found. It is a change to the experiment's constants and therefore a founder decision, so
it is recorded here and not applied.
