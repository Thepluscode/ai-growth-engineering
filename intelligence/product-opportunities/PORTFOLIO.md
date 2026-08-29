# Product Opportunity Portfolio — 2026-08-29

## Premise result

The product gate was run against every offer currently preserved in `seeds/registries.json`.
There are five named candidates. There are not 20–30 evidence-backed opportunities, so the
portfolio is not padded with invented buyers or demand.

| Opportunity | Observed evidence | Hard-gate result | Missing premise inputs |
| --- | --- | --- | --- |
| Growth Leak Teardown | `EV-ACQ-VERDICT-01`, `EV-ACQ-RECIPIENT-01`, `EV-OFFER-CONFLICT-01` | RESEARCH | demand signal, viable distribution path, economics hypothesis |
| Pipeline Engineering Sprint | `EV-ACQ-VERDICT-01`, `EV-OFFER-CONFLICT-01` | RESEARCH | demand signal, distribution path, validation test, economics hypothesis |
| AI Compliance Diagnostic | no direct evidence | RESEARCH | evidence, demand signal, distribution path, validation test, economics hypothesis |
| Architecture Assessment | no direct evidence | RESEARCH | evidence, demand signal, distribution path, validation test, economics hypothesis |
| Security Questionnaire Rescue Sprint | `EV-OFFER-REGISTRY-GAP-01`, `EV-OFFER-CONFLICT-01`, `EV-SITE-CONGRUENCE-02`, `EV-BASELINE-03` | RESEARCH | demand signal, economics hypothesis |

No candidate passes the non-compensatory gate, so no priority scores or “top three” are reported.
Ranking unsupported ideas would manufacture confidence. The next unit of progress is a named buyer
making a measurable purchase action, not another product feature.

## Observed, inferred, unknown

### Observed

- The teardown route produced 0 meaningful replies from 48 reachable role inboxes; two named-buyer
  sends are too small to conclude (`EV-ACQ-VERDICT-01`, `EV-ACQ-RECIPIENT-01`).
- The Rescue Sprint is a fixed £1,500 offer on the live site, but it has 0 sends and 0 buyers
  (`EV-OFFER-REGISTRY-GAP-01`, `EV-OFFER-CONFLICT-01`).
- The owned site receives about 47 visitors per month and has no observed referrers
  (`EV-BASELINE-03`).
- The AI Compliance Diagnostic and Architecture Assessment are offers in the registry, not observed
  demand.

### Inferred

- The Rescue Sprint is the closest candidate to validation because its offer, price, purchase action,
  and test can be named. That does not make its demand or economics true.
- Manual delivery is the smallest justified format for the Rescue Sprint. A static, manually prepared
  asset remains the smallest justified format for the free teardown.

### Unknown

- Whether any named buyer will pay for any of the five offers.
- Delivery time, gross margin, support burden, recurrence, expansion, and retained value.
- A distribution path that can reach enough qualified buyers for a fixed test.

## Decision lineage

```text
IDEA → EVIDENCE → OPPORTUNITY → OFFER → MINIMUM COMMERCIAL UNIT
     → PURCHASE → USAGE → OUTCOME → EXPANSION
```

The five candidates stop between OFFER and PURCHASE. They must not be described as products with
validated demand.

## Productisation rule

Move only as evidence requires:

```text
insight → content → free tool → paid asset → manual service
        → repeatable workflow → automation → software → platform
```

The Growth Command Center remains a `HYPOTHESIS` in `capability_map.json`. There is not yet enough
repeated, trustworthy operating data to make its dashboard anything other than a projection.

## Opportunity Graveyard

Empty. None of the five ideas has failed a product-level purchase test. The shared-inbox outbound
route failed its acquisition threshold; that is not evidence that the underlying offers are dead.
When an opportunity does fail a fixed test, preserve its reason, decision date, and observable reopen
condition in the registry rather than deleting it.
