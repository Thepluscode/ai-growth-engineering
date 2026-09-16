# EXP-ACQ-0007 — governed external message procedure vs the incumbent

**Preregistered:** 2026-09-16 · **Status:** contract frozen · **0 messages generated, 0 sent, 0 contacts enriched**

One variable: the procedure that generates the first-touch message. Everything else — cohort,
channel, sender, offer, personalisation standard, timing policy — is held constant across both arms.

## Arms

| Arm | Procedure | Content hash | Identity |
|---|---|---|---|
| `baseline` | `theplus.outreach-research@1.0.0` | `11ab2c98269de8b07cb0d03e729a21a83acb4c2a1860546244cea923abece66e` | incumbent, already registered |
| `candidate` | `marketingskills_cold_email@2.0.0` | `5736b9db5a5b2f6ab760dd9b5729393b14dc5e08f5651f186405d751c306bbd6` | admitted 2026-09-16 via the External Skill Supply Chain |

The candidate entered through the governed export
`4099bfa70e02ba02faf52a9fa60d040d49374959ffe1918aa3e2b066d8b9f6d8`, approved by the founder for
**`message_generation` only**. Explicitly **not** approved, and therefore not exercised anywhere in
this experiment: follow-up sequencing · bulk or volume guidance · autonomous sending ·
personalisation claims not grounded in observed evidence · any override of `GrowthActionPolicy` or
the existing outreach controls.

Both identities are frozen in `experiment_procedures` as `VARIABLE`, one per arm, at
**2026-09-16T12:03:34+00:00**. An exposure dated before that is rejected by the evaluator, not
counted.

## Cohort

60 accounts, frozen before randomisation. Qualification rule, unchanged from the one in force when
the cohort was built:

> UK active legal entity · live first-party site · clear MSP / cyber / IT-services offer ·
> repeatable B2B motion · named current decision-maker · at least 4 commercial-complexity signals.
> BORDERLINE does not count.

Integrity, checked against the frozen file before the draw:

| Check | Result |
|---|---|
| Exactly 60 rows | 60 |
| Unique domains | 60 |
| Unique company numbers | 60 |
| Overlap with the prior-contact exclusion list (94 rows) | 0 |
| Every entity active on the register | yes |
| Every account names a current officer | yes |
| RESERVE, BORDERLINE or unresolved-fetch accounts included | none |

`cohort.csv` carries public-register identity only. Officer names and the free-text qualification
notes stay in the local working file — this repository is public. The local file is
`sha256 94e38c8cf8e674c86ed420a78c6b2a45c8fda6f6bd9d593ed80c5c69a7a52275`; the committed
`cohort.csv` is `sha256 fe18f1864b67dd92f1c4e8fed5a98270dea321d7421b4998950200d90cd0fdb8`.

### Accounts qualified but outside the cohort, recorded before this contract was frozen

Neither is added or swapped in now; both are named here so the exclusion is on the record rather
than invisible.

| Account | Number | Status | Reason |
|---|---|---|---|
| ITbuilder | `04296864` | `QUALIFIED - FLAG` | five directors appointed within three months; still trades under its own brand and site. Held for a founder call on whether it remains standalone. Excluded before this preregistration, not after seeing the draw |
| Fruition Systems | `04522004` | `QUALIFIED (RESERVE)` | weakest evidence in the set, no certifications; held as a reserve, never a core member |

### Covariates — recorded, never used to exclude

Two accounts carry caution flags. Both stay in. The flags are recorded as covariates and are
reported alongside the result; they are not exclusions and not adjustment terms.

| Account | Covariate | What was observed |
|---|---|---|
| Dynamic Networks Group `06790995` | `site_leadership_stale` | the site names a former CEO; the register shows him resigned 2026-02-06, current directors are two other people |
| CCT Systems `09122489` | `recent_control_change` | sole current director appointed 2026-04-01 |
| Cirrus MSP `15874423`, Impelling `14717014` | `recent_incorporation` | incorporated Aug 2024 and Mar 2023 |
| IT Foundations `SC212586`, Mear Technology `SC404950` | `scottish_registration` | registered in Scotland |
| DigitalXRAID `09809709` | `recent_multi_director_change` | four directors appointed across 2025–2026 |

## Randomisation

Drawn once, on 2026-09-16, before any message existed.

```
seed       = "EXP-ACQ-0007/2026-09-16"
input      = the 60 company numbers, sorted ascending as strings
key(n)     = sha256(seed + "|" + n)          # hex
order      = sort by (key, n)
arms       = first 30 -> candidate, last 30 -> baseline
```

No RNG: a keyed sort reproduces byte-identically in any language and any runtime version. The
`assignment_key` column in `assignment.csv` is that digest, so the draw can be recomputed from the
seed alone and checked row by row.

| | |
|---|---|
| Seed | `EXP-ACQ-0007/2026-09-16` |
| Algorithm | SHA-256 keyed sort (above); no random number generator |
| Runtime | CPython 3.12, `hashlib`; result is runtime-independent by construction |
| Input hash (sorted company numbers) | `8cc4bf9bd5ba2797ea9e3d13429fd1af5d6c76dd18204f7797c606b20506a6cd` |
| Assignment hash (`assignment.csv`) | `6ccd4dfcda514b6b85d14c801a6eb250d357df749451ba10f442b1e1364b4bf5` |
| Drawn at | 2026-09-16 |
| Result | candidate 30 · baseline 30 |

**The draw is not repeated.** It was run once and recorded. It will not be redrawn because an arm
looks uneven, and the balance table below is a diagnostic, never an objective.

### Balance — reported, not optimised against

| Arm | n | Mean complexity signals | Covariates drawn into this arm |
|---|---|---|---|
| candidate | 30 | 7.13 | `recent_incorporation` ×2 |
| baseline | 30 | 6.20 | `site_leadership_stale`, `recent_control_change`, `recent_multi_director_change`, `scottish_registration` ×2 |

Both caution-flagged accounts drew into `baseline`. That is what the seed produced and it stands.

## Primary metric

**`qualified_reply_rate`** — AGE's existing controlled-effect metric, already the primary metric of
`EXP-ACQ-0001` and `EXP-ACQ-0002` under its alias `meaningful_reply_rate`
(`METRIC_ALIASES` resolves the two to one quantity). No new metric is defined here.

- Denominator: **matured delivered exposures**, counted by the segment unit model — an exposure
  matures 14 days after delivery (`EVIDENCE_POLICY["response_window_days"]`).
- Numerator: `qualified_replies`, counted the way every other AGE experiment counts them.
- Secondary, reported and never decisive: `reply_rate`, `meeting_rate`.

Thresholds carried over unchanged from `EXP-ACQ-0001`/`-0002` so the numbers stay comparable across
this repository's acquisition experiments: success `0.10`, review `0.05`, minimum sample `60`.

## Decision rule

The verdict is the procedure evaluator's, not a single-arm threshold. It returns `CONTROLLED_EFFECT`
only when **all** hold: the procedure was the declared variable of concurrent arms in one
experiment · each side has ≥30 matured delivered exposures · no competing variable differs between
the sides · no synthetic data · every exposure postdates the binding · `|z| ≥ 1.96` on the primary
metric. `CONTROLLED_EFFECT → KEEP`; `REGRESSION`/`NO_DIFFERENCE → REJECT`;
`DESCRIPTIVE_DIFFERENCE`/`CONFOUNDED → ITERATE`; `INSUFFICIENT_SAMPLE`/`IMMATURE`/`NOT_EVALUABLE →
NEED_MORE_DATA`. A `KEEP` returns the result file to the Intelligent Machine for human promotion
review; nothing here adopts or widens the procedure on its own.

## What 30 per arm can and cannot decide — the arithmetic, done before freezing

| Baseline qualified replies | Candidate needs, for z ≥ 1.96 | That candidate rate |
|---|---|---|
| 1/30 (3.3%) | 6/30 | 20.0% |
| 2/30 (6.7%) | 8/30 | 26.7% |
| 3/30 (10.0%) | 10/30 | 33.3% |
| 4/30 (13.3%) | 11/30 | 36.7% |

At a 10% baseline the minimum detectable difference at 80% power is **21.7%**, against a
`max_detectable_difference` policy line of 10%. Two consequences, stated now rather than discovered
in the analysis:

1. **A null result here returns `INSUFFICIENT_SAMPLE`, never `NO_DIFFERENCE`.** This experiment
   cannot conclude the two procedures perform alike. It can only detect a large effect.
2. **The sample has no slack.** Each side needs 30 matured delivered exposures and each side has
   exactly 30 accounts. One bounce, one undeliverable or one account that never matures drops that
   side below the denominator floor and the evaluator returns `INSUFFICIENT_SAMPLE` for the whole
   comparison. No account is substituted to repair this after the fact.

The design is preregistered as specified regardless. What it buys is a clean, governed,
single-variable comparison whose only honest outcomes are `CONTROLLED_EFFECT` (a large real effect)
or `NEED_MORE_DATA`.

## What this contract does not authorise

No sending. No invitations. No email. No sequence activation. No message publication. No contact
enrichment that consumes credits. Message generation itself is a separate step and has not run:
this contract freezes the cohort, the draw and the analysis, and stops.
