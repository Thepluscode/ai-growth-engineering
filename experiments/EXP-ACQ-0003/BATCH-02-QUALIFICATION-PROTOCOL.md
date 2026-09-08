# Batch-02 qualification protocol

**Preregistered:** 2026-09-08 · **Status:** frozen before any candidate was reviewed

Fixed in advance because a qualification rule written after seeing the candidates is a
description of the candidates. The 40 sourced candidates have not been assessed against
anything at the time of writing.

## The question this protocol asks

> Does public evidence indicate that this business is large and commercially active enough
> for the acquisition problem under test to plausibly exist?

It does **not** ask whether the business has that problem. Nothing observable from outside
establishes internal acquisition pain, and inferring it would manufacture the finding the
experiment is meant to earn. Qualification establishes **eligibility to be asked**, nothing
more.

## Director count is not a qualification rule

An earlier draft proposed rejecting single-director companies. That is wrong and is
withdrawn: **Companies House board size is not workforce size.** A one-director company can
carry 10–30 staff, a sales function, a marketing function, poor acquisition and a real
£1,500–£3,000 willingness to pay. Rejecting on board size replaces one bad proxy with
another.

Ownership structure is recorded as an **observational field**, never a gate:

```
ownership_structure: SINGLE_DIRECTOR | MULTI_DIRECTOR
```

It is kept precisely so it can be compared later — LinkedIn identity rate, invitation
acceptance, reply rate, confirmed pain, proposal rate — across the two cohorts. Founder-led
firms may prove dramatically easier to reach than management-led ones, or may reply and then
prove unable to afford the offer. Both are findings. Deleting the cohort forecloses both.

## Hard requirements — all five must hold

```
1. ACTIVE UK LEGAL ENTITY
2. LIVE FIRST-PARTY WEBSITE
3. CLEAR MSP / CYBERSECURITY / IT-SERVICES OFFER
4. EVIDENCE OF A REPEATABLE B2B COMMERCIAL MOTION
5. NAMED CURRENT HUMAN DECISION-MAKER
```

Requirement 4 is the discriminating one. It separates

```
founder + laptop          from          small operating company with a revenue engine
```

without pretending to know either one's internal pipeline.

## Commercial-complexity signals (evidence for requirement 4)

Counted from first-party pages only. Each signal counts once, however many times it appears.

| Signal | What is observed |
|---|---|
| `service_lines` | three or more distinct service pages |
| `recurring_packages` | named managed-service tiers, plans, or per-user/per-month pricing |
| `case_studies` | a case-study or customer-story page |
| `named_customers` | customers named or logo wall |
| `accreditations` | ISO 27001/9001, Cyber Essentials, IASME, CREST, vendor partner tiers |
| `commercial_roles` | sales, account-management or marketing staff named or advertised |
| `multiple_offices` | more than one UK address |
| `vertical_offerings` | sector-specific pages (legal, finance, healthcare, education…) |
| `procurement_frameworks` | G-Cloud, CCS, NHS or other framework participation |
| `active_hiring` | a careers page carrying at least one current role |
| `booking_funnel` | book-a-call, demo, or audit booking route distinct from a contact form |
| `sustained_content` | a blog or resources section with three or more dated items |

## Classification, with thresholds fixed now

```
QUALIFIED    all 5 hard requirements AND >= 4 distinct complexity signals
BORDERLINE   all 5 hard requirements AND 2-3 complexity signals
REJECTED     any hard requirement fails, OR <= 1 complexity signal
```

**BORDERLINE does not count as qualified** and is not seeded into the experiment
population. It is a real operating business whose commercial complexity is unresolved from
outside, and forcing it to either extreme would corrupt the denominator. Borderline accounts
are held for a human read.

Every decision records the signals observed and the URL each was observed on. A rejection
records its reason; a rejection without one is a deletion.

## Absence of a signal is not absence of the thing

A homepage without a certification logo is not an uncertified company, and a site with no
careers page is not a company that is not hiring. These signals measure **observable
commercial surface**, which is what an outbound experiment can act on. Where the count sits
near a threshold that limitation is the reason BORDERLINE exists.

## Incorporation age is a sampling heuristic, not a market finding

The pre-2020 incorporation bound used to source these candidates is recorded as:

```
SAMPLING HEURISTIC
Chosen before any acceptance outcome was observed, to raise the prior probability of
operational maturity in the batch.
```

It is **not**:

```
MARKET FINDING
Recent incorporations are poor prospects for this route.
```

The evidence behind it is three companies — cyberISMS, Fortitude Cyber, Aursec, all
incorporated 2024–25 — that failed LinkedIn identity verification. Three observations
cannot establish a general rule about incorporation age, and treating a search optimisation
as a business truth is how a convenience becomes a belief. The observation is preserved; the
inference is marked unvalidated and remains open.

## What this protocol does not authorise

No invitation. No message. No subscription. No inference of an email address. Qualification
is desk research against public pages, and it stops there.
