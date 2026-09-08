# Batch-02 qualification — result

**Run:** 2026-09-08 · **Protocol:** `BATCH-02-QUALIFICATION-PROTOCOL.md`, frozen before review

## Answer

| | |
|---|---|
| Candidates reviewed | 40 |
| **QUALIFIED** | **10 (25.0%)** |
| BORDERLINE | 10 |
| REJECTED | 20 |
| QUALIFIED with a LinkedIn identity resolved | **7 of 10 (70.0%)** |

Only the 10 QUALIFIED were seeded, as `qualified_batch_07`. Borderline and rejected
candidates were not written to `prospects`.

## Rejecting single-director firms would have been wrong

The earlier draft proposed it. Withdrawn before review, and the data says the withdrawal
was right:

| Ownership | Qualified | Rate |
|---|---|---|
| SINGLE_DIRECTOR | 5 of 23 | 22% |
| MULTI_DIRECTOR | 5 of 16 | 31% |

**Fisher exact, two-tailed: p = 0.71.** The difference is not distinguishable from chance at
this sample size, and **half of every qualified account would have been deleted** by the
rule. `ownership_structure` is retained as an observational field so the cohorts can be
compared at acceptance, reply and proposal — where a real difference may yet appear.

## Rejection reasons

| Count | Reason |
|---|---|
| 7 | no MSP / cyber / IT-services offer on the site |
| 6 | only 1 commercial-complexity signal |
| 5 | 0 commercial-complexity signals |
| 1 | no named current director on the register |
| 1 | site did not return 200 on re-fetch |

Eighteen of 20 rejections are the filter working as intended: a live domain with a company
name on it is not an MSP with a revenue engine.

## Which signals actually discriminated

Among the 10 QUALIFIED: `sustained_content` 9, `case_studies` 7, `accreditations` 7,
`commercial_roles` 6, `service_lines` 6, `recurring_packages` 5. Rare:
`procurement_frameworks` 1, `active_hiring` 1.

Sustained content and case studies are doing most of the discriminating. Both are cheap to
fake and neither proves commercial complexity on its own — which is the reason the protocol
requires four independent signals rather than any single one.

## The funnel, with denominators intact

```
$ age sourcing-funnel
run BATCH-02
  Register candidate to website-evidenced       40/316       12.7%
  Website-evidenced to QUALIFIED                10/40        25.0%
  QUALIFIED to LinkedIn identity                 7/10        70.0%
  compound: register -> LinkedIn identity                   2.215%
```

95% CIs: 9.4–16.8%, 14.2–40.2%, 39.7–89.2%. The last two rest on 40 and 10 observations
and are correspondingly wide.

## Supply against the 100-account target

| | |
|---|---|
| QUALIFIED accounts holding a LinkedIn identity | **39** |
| Target | 100 |
| Shortfall | 61 |
| Raw register companies required at the measured 2.215% | **2,754** |
| — if every step lands at its CI high (6.02%) | 1,014 |
| — if every step lands at its CI low (0.53%) | 11,485 |

**The requirement exceeds the reachable pool.** The six token/SIC combinations currently
searched hold roughly 1,411 companies in total. Reaching 100 therefore needs the sourcing
*widened* — more name tokens, more SIC codes, or relaxing the pre-2020 bound — not merely
paged more deeply. That is a decision, and it is not taken here.

Note the correction: 46 accounts hold a LinkedIn identity, but only **39 of them are
QUALIFIED**. Seven identities sit on rows that were never qualified — the same defect the
scoreboard fix removed, appearing one stage further down.

## Classifications


### QUALIFIED

| Company | Signals | Ownership | Identity | Reason |
|---|---|---|---|---|
| Cyber Chain Alliance | 8 | single | **unresolved** | 8 commercial-complexity signals |
| North London IT Support | 7 | multi | resolved | 7 commercial-complexity signals |
| IT Support 365 | 7 | single | **unresolved** | 7 commercial-complexity signals |
| Cyber Distribution | 5 | multi | resolved | 5 commercial-complexity signals |
| Cambridge Cyber | 5 | single | resolved | 5 commercial-complexity signals |
| Dovetail IT Support | 5 | multi | resolved | 5 commercial-complexity signals |
| Managed IT Experts | 5 | single | resolved | 5 commercial-complexity signals |
| Proteus-Cyber | 4 | multi | resolved | 4 commercial-complexity signals |
| Hero IT Support | 4 | single | resolved | 4 commercial-complexity signals |
| Rapid IT Support | 4 | multi | **unresolved** | 4 commercial-complexity signals |

### BORDERLINE

| Company | Signals | Ownership | Identity | Reason |
|---|---|---|---|---|
| Ascent Cyber Ltd | 3 | single | — | 3 commercial-complexity signals (2-3 band) |
| Secure Cyber Ltd | 3 | single | — | 3 commercial-complexity signals (2-3 band) |
| One Brightly Cyber Ltd | 3 | multi | — | 3 commercial-complexity signals (2-3 band) |
| It Biz Support Limited | 3 | single | — | 3 commercial-complexity signals (2-3 band) |
| Urban It Support Ltd | 3 | single | — | 3 commercial-complexity signals (2-3 band) |
| Cyber Security Specialists Limited | 2 | multi | — | 2 commercial-complexity signals (2-3 band) |
| It Support North West Limited | 2 | single | — | 2 commercial-complexity signals (2-3 band) |
| Smart Computers It Support Limited | 2 | multi | — | 2 commercial-complexity signals (2-3 band) |
| One Stop It Support Ltd | 2 | single | — | 2 commercial-complexity signals (2-3 band) |
| E-Volve It Support Limited | 2 | single | — | 2 commercial-complexity signals (2-3 band) |

### REJECTED

| Company | Signals | Ownership | Identity | Reason |
|---|---|---|---|---|
| Cyber-Duck Limited | 5 | multi | — | no MSP/cyber/IT service offer on site |
| E2E-Cyber Limited | 1 | single | — | only 1 commercial-complexity signal(s) |
| Cyber Sharp I.T Limited | 1 | multi | — | only 1 commercial-complexity signal(s) |
| Quorum Cyber Security Limited | 1 | multi | — | only 1 commercial-complexity signal(s) |
| Dragon It Support Limited | 1 | single | — | only 1 commercial-complexity signal(s) |
| Re It Support Limited | 1 | single | — | only 1 commercial-complexity signal(s) |
| It Support Berkshire Limited | 1 | single | — | only 1 commercial-complexity signal(s) |
| Chelmer It Support Ltd | 1 | single | — | no MSP/cyber/IT service offer on site |
| Cyber Sheku Limited | 0 | single | — | only 0 commercial-complexity signal(s) |
| Cyber Security (N.I.) Ltd | 0 | multi | — | only 0 commercial-complexity signal(s) |
| Global Cyber Consultants Ltd | 0 | multi | — | no MSP/cyber/IT service offer on site |
| Cyber Leader Ltd | 0 | single | — | no MSP/cyber/IT service offer on site |
| Secure Cyber Solutions Limited | 0 | multi | — | only 0 commercial-complexity signal(s) |
| Smart Cyber Cafe Ltd | 0 | single | — | no MSP/cyber/IT service offer on site |
| Cyber Resilience Consulting Ltd | 0 | single | — | no MSP/cyber/IT service offer on site |
| Cyber Defence Alliance Limited | 0 | multi | — | only 0 commercial-complexity signal(s) |
| It Help Support Limited | 0 | multi | — | no MSP/cyber/IT service offer on site |
| Quest It Support Limited | 0 | none | — | no named current director on the register |
| Kings Lynn It Support Ltd | 0 | single | — | only 0 commercial-complexity signal(s) |
| Oxon It Support Ltd | 0 | single | — | site did not return 200 on re-fetch |
## Not done

No invitation sent. No subscription bought. No message written. No email inferred. Borderline
accounts remain unseeded and unqualified.
