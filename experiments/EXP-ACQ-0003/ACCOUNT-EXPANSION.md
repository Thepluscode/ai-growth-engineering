# Account list expansion — sourced candidates

**Run:** 2026-09-08 · **Status:** candidates, **nothing qualified, nothing seeded**

`EXP-ACQ-0003/IDENTITY-VERIFICATION.md` landed in the contract's **ADJUST** band: 39 verified
accounts cannot reach 29 accepts, the constraint is the size of the account list, and a
subscription would fix the invitation rather than the shortage. This is that expansion, taken
as far as it can honestly go without a person reading a website.

## These are not qualified accounts, and they are not in the store

`scoreboard.qualified_prospects` counts **every** prospect row whose status is not
`disqualified%`. Seeding 40 unreviewed candidates would have moved a VERIFIED number from 51
to 91 by adding accounts nobody qualified — the exact "fill the gap to tidy the table" failure.
So the candidates live here and in `candidates.csv`, and enter `prospects` only after a person
applies the Batch-02 qualification rule to each one.

## Method

**Pool** — Companies House advanced search: SIC 62020/62090, status active, incorporated on or
before 2019-12-31, company name containing `cyber`, `it support` or `managed it`. The date bound
is deliberate: cyberISMS, Fortitude Cyber and Aursec were all incorporated 2024–25 and all three
failed LinkedIn identity verification, so recent incorporations are known to be a dead end for
this route. 316 companies after de-duplication against the 63 already on file.

**Website** — a guessed domain is a hypothesis; the fetched page is the evidence. A candidate
keeps a website only where the live page's own `<title>` names the company. Nothing is recorded
from a guess that was not fetched.

**Filter** — the homepage must show an **acquisition route** (a contact route or CTA) *and*
**managed-service** language. Delivery proof and UK presence are recorded where seen but do not
gate, because absence of a certification logo on a homepage is not absence of the certification.

## Result

| | |
|---|---|
| Pooled from the register | 316 |
| Live site whose title names the company, with route + service | **40 (12.7%)** |
| Of those, carrying at least one current director | **39** |
| Named directors available | 64 (mean **1.6** per company) |

## The quality signal a reviewer should look at first

**Mean 1.6 directors, against 2.8 across the existing 51.** Twenty-three of the 39 have exactly
one. These are materially smaller firms than the current book — which cuts both ways, and the
decision is not mine to make:

- The founder *is* the commercial buyer, so identity resolution should be easier than the 76.5%
  achieved on the existing list, and there is no gatekeeper.
- A one-director firm may be too small to have the acquisition problem the £1,500 offer
  addresses. `EXP-ACQ-0001`'s wedge assumes an acquisition function that is failing, not one
  that does not exist.

If the reviewer rejects the single-director firms, the usable expansion is **16 accounts**, not
40. That number should be decided before, not after, seeing the accept rate.

## Candidates

Director names are **not listed**: this repository is public, and a statutory register does not
make a publishable prospect list. Counts only.

| Company | Website | Register | Directors | Homepage signals observed |
|---|---|---|---|---|
| Ascent Cyber Ltd | [ascentcyber.co.uk](https://ascentcyber.co.uk) | [SC628336](https://find-and-update.company-information.service.gov.uk/company/SC628336) | 1 | acquisition_route, delivery_proof, managed_service, uk_presence |
| Cambridge Cyber Limited | [cambridgecyber.co.uk](https://cambridgecyber.co.uk) | [10181626](https://find-and-update.company-information.service.gov.uk/company/10181626) | 1 | acquisition_route, managed_service, uk_presence |
| Chelmer It Support Ltd | [chelmeritsupport.co.uk](https://chelmeritsupport.co.uk) | [07808188](https://find-and-update.company-information.service.gov.uk/company/07808188) | 1 | acquisition_route, managed_service, uk_presence |
| Cyber Chain Alliance Ltd | [cyberchainalliance.com](https://cyberchainalliance.com) | [11706569](https://find-and-update.company-information.service.gov.uk/company/11706569) | 1 | acquisition_route, delivery_proof, managed_service, uk_presence |
| Cyber Defence Alliance Limited | [cyberdefencealliance.co.uk](https://cyberdefencealliance.co.uk) | [09899234](https://find-and-update.company-information.service.gov.uk/company/09899234) | 6 | acquisition_route, managed_service, uk_presence |
| Cyber Distribution Ltd | [cyberdistribution.co.uk](https://cyberdistribution.co.uk) | [11246527](https://find-and-update.company-information.service.gov.uk/company/11246527) | 3 | acquisition_route, managed_service, uk_presence |
| Cyber Leader Ltd | [cyberleader.co.uk](https://cyberleader.co.uk) | [11326898](https://find-and-update.company-information.service.gov.uk/company/11326898) | 1 | acquisition_route, managed_service |
| Cyber Resilience Consulting Ltd | [cyberresilienceconsulting.com](https://cyberresilienceconsulting.com) | [10250473](https://find-and-update.company-information.service.gov.uk/company/10250473) | 1 | acquisition_route, delivery_proof, managed_service |
| Cyber Security (N.I.) Ltd | [cybersecurityni.com](https://cybersecurityni.com) | [NI647179](https://find-and-update.company-information.service.gov.uk/company/NI647179) | 4 | acquisition_route, delivery_proof, managed_service, uk_presence |
| Cyber Security Specialists Limited | [cybersecurityspecialists.co.uk](https://cybersecurityspecialists.co.uk) | [09563339](https://find-and-update.company-information.service.gov.uk/company/09563339) | 2 | acquisition_route, delivery_proof, managed_service, uk_presence |
| Cyber Sharp I.T Limited | [cybersharpit.co.uk](https://cybersharpit.co.uk) | [10653984](https://find-and-update.company-information.service.gov.uk/company/10653984) | 2 | acquisition_route, delivery_proof, managed_service, uk_presence |
| Cyber Sheku Limited | [cybersheku.co.uk](https://cybersheku.co.uk) | [11829605](https://find-and-update.company-information.service.gov.uk/company/11829605) | 1 | acquisition_route, delivery_proof, managed_service, uk_presence |
| Cyber-Duck Limited | [cyberduck.co.uk](https://cyberduck.co.uk) | [04356226](https://find-and-update.company-information.service.gov.uk/company/04356226) | 2 | acquisition_route, delivery_proof, managed_service |
| Dovetail It Support Limited | [dovetailitsupport.com](https://dovetailitsupport.com) | [09860629](https://find-and-update.company-information.service.gov.uk/company/09860629) | 2 | acquisition_route, delivery_proof, managed_service, uk_presence |
| Dragon It Support Limited | [dragonitsupport.co.uk](https://dragonitsupport.co.uk) | [06794018](https://find-and-update.company-information.service.gov.uk/company/06794018) | 1 | acquisition_route, managed_service, uk_presence |
| E-Volve It Support Limited | [evolveitsupport.co.uk](https://evolveitsupport.co.uk) | [08726677](https://find-and-update.company-information.service.gov.uk/company/08726677) | 1 | acquisition_route, delivery_proof, managed_service, uk_presence |
| E2E-Cyber Limited | [e2ecyber.com](https://e2ecyber.com) | [08732949](https://find-and-update.company-information.service.gov.uk/company/08732949) | 1 | acquisition_route, delivery_proof, managed_service |
| Global Cyber Consultants Ltd | [globalcyberconsultants.com](https://globalcyberconsultants.com) | [11229097](https://find-and-update.company-information.service.gov.uk/company/11229097) | 2 | acquisition_route, managed_service |
| Hero It Support Ltd | [heroitsupport.com](https://heroitsupport.com) | [05685764](https://find-and-update.company-information.service.gov.uk/company/05685764) | 1 | acquisition_route, delivery_proof, managed_service |
| It Biz Support Limited | [itbizsupport.co.uk](https://itbizsupport.co.uk) | [08845673](https://find-and-update.company-information.service.gov.uk/company/08845673) | 1 | acquisition_route, delivery_proof, managed_service, uk_presence |
| It Help Support Limited | [ithelpsupport.com](https://ithelpsupport.com) | [09345042](https://find-and-update.company-information.service.gov.uk/company/09345042) | 2 | acquisition_route, managed_service |
| It Support 365 Ltd | [itsupport365.co.uk](https://itsupport365.co.uk) | [06678853](https://find-and-update.company-information.service.gov.uk/company/06678853) | 1 | acquisition_route, delivery_proof, managed_service, uk_presence |
| It Support Berkshire Limited | [itsupportberkshire.com](https://itsupportberkshire.com) | [07858650](https://find-and-update.company-information.service.gov.uk/company/07858650) | 1 | acquisition_route, managed_service, uk_presence |
| It Support North West Limited | [itsupportnorthwest.co.uk](https://itsupportnorthwest.co.uk) | [08613627](https://find-and-update.company-information.service.gov.uk/company/08613627) | 1 | acquisition_route, delivery_proof, managed_service, uk_presence |
| Kings Lynn It Support Ltd | [kingslynnitsupport.co.uk](https://kingslynnitsupport.co.uk) | [08233866](https://find-and-update.company-information.service.gov.uk/company/08233866) | 1 | acquisition_route, managed_service, uk_presence |
| Managed It Experts Ltd | [manageditexperts.co.uk](https://manageditexperts.co.uk) | [SC348738](https://find-and-update.company-information.service.gov.uk/company/SC348738) | 1 | acquisition_route, delivery_proof, managed_service, uk_presence |
| North London It Support Ltd | [northlondonitsupport.com](https://northlondonitsupport.com) | [07231060](https://find-and-update.company-information.service.gov.uk/company/07231060) | 2 | acquisition_route, delivery_proof, managed_service, uk_presence |
| One Brightly Cyber Ltd | [onebrightlycyber.com](https://onebrightlycyber.com) | [11736822](https://find-and-update.company-information.service.gov.uk/company/11736822) | 2 | acquisition_route, delivery_proof, managed_service, uk_presence |
| One Stop It Support Ltd | [onestopitsupport.co.uk](https://onestopitsupport.co.uk) | [11735790](https://find-and-update.company-information.service.gov.uk/company/11735790) | 1 | acquisition_route, delivery_proof, managed_service, uk_presence |
| Oxon It Support Ltd | [oxonitsupport.co.uk](https://oxonitsupport.co.uk) | [07463868](https://find-and-update.company-information.service.gov.uk/company/07463868) | 1 | acquisition_route, delivery_proof, managed_service, uk_presence |
| Proteus-Cyber Ltd | [proteuscyber.com](https://proteuscyber.com) | [07239733](https://find-and-update.company-information.service.gov.uk/company/07239733) | 2 | acquisition_route, managed_service, uk_presence |
| Quest It Support Limited | [questitsupport.co.uk](https://questitsupport.co.uk) | [SC516437](https://find-and-update.company-information.service.gov.uk/company/SC516437) | 0 | acquisition_route, managed_service, uk_presence |
| Quorum Cyber Security Limited | [quorumcybersecurity.co.uk](https://quorumcybersecurity.co.uk) | [SC510322](https://find-and-update.company-information.service.gov.uk/company/SC510322) | 3 | acquisition_route, delivery_proof, managed_service, uk_presence |
| Rapid It Support Ltd | [rapiditsupport.co.uk](https://rapiditsupport.co.uk) | [11853245](https://find-and-update.company-information.service.gov.uk/company/11853245) | 2 | acquisition_route, managed_service, uk_presence |
| Re It Support Limited | [reitsupport.co.uk](https://reitsupport.co.uk) | [04892198](https://find-and-update.company-information.service.gov.uk/company/04892198) | 1 | acquisition_route, delivery_proof, managed_service, uk_presence |
| Secure Cyber Ltd | [securecyber.co.uk](https://securecyber.co.uk) | [12287409](https://find-and-update.company-information.service.gov.uk/company/12287409) | 1 | acquisition_route, delivery_proof, managed_service, uk_presence |
| Secure Cyber Solutions Limited | [securecybersolutions.co.uk](https://securecybersolutions.co.uk) | [10325687](https://find-and-update.company-information.service.gov.uk/company/10325687) | 2 | acquisition_route, managed_service, uk_presence |
| Smart Computers It Support Limited | [smartcomputersitsupport.co.uk](https://smartcomputersitsupport.co.uk) | [10074950](https://find-and-update.company-information.service.gov.uk/company/10074950) | 3 | acquisition_route, delivery_proof, managed_service, uk_presence |
| Smart Cyber Cafe Ltd | [smartcybercafe.com](https://smartcybercafe.com) | [08772423](https://find-and-update.company-information.service.gov.uk/company/08772423) | 1 | acquisition_route, managed_service |
| Urban It Support Ltd | [urbanitsupport.com](https://urbanitsupport.com) | [07948984](https://find-and-update.company-information.service.gov.uk/company/07948984) | 1 | acquisition_route, delivery_proof, managed_service, uk_presence |
## Pool depth remaining

`cyber` + SIC 62020 alone returns **858** active companies incorporated by 2019; this run read
six pages per token/SIC combination. Deeper paging is available and needs no new method — the
limit here was time, not supply.

## Not done

Nothing qualified. Nothing seeded into `prospects`. No teardown written, no identity resolved,
no contact made.
