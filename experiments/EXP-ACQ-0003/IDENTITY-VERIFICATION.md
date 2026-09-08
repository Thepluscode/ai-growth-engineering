# LinkedIn identity verification — result

**Run:** 2026-09-08 · **Contract:** `PREREGISTRATION.md` admission rule (2)

Admission rule (2) requires a commercial decision-making role evidenced on the person's own
LinkedIn profile: a statutory appointment alone does not admit an account, because the
register publishes the office and never the function.

## Answer

**39 of 51 non-disqualified accounts now carry a LinkedIn identity. 48 identities persisted.**

| | |
|---|---|
| Non-disqualified accounts | 51 |
| Accounts with a LinkedIn identity | **39 (76.5%)** |
| — two-source: register **and** profile agree | **26** |
| — single-source: profile only, register could not corroborate | 13 |
| Accounts with none | 12 |
| Identities persisted | 48 |

Every identity is stored as **`observed_published`**, never `verified`. A profile page was
read; a person was not contacted. Two-source records carry confidence 0.8, single-source 0.6.

## What "two-source" means, and why it changed answers

The register names the statutory director; the LinkedIn profile carries that person's name
with the company in its own title or URL. Requiring both **corrected the search on its own
terms**, twice:

| Account | Search alone proposed | Register + profile | |
|---|---|---|---|
| ADL Consulting | Andrew Landells, **New Zealand** | Andy Larkum, `andy-larkum-925660b` | search was wrong |
| Technical Drive | Amie Johnson, "digital director" | Simon Cole, `simon-cole-7a013042` | not a director at all |

Search alone also proposed rival entities for Wavex (Indian and Australian "WaveX"), HBP
(US and South African), TWC (Dutch), BCN (Indian) and Blue Frontier (a US air-conditioning
firm). The register removed all of them. Where the register **disagreed** — Chorus returns
Nicola Saner as MD while the register lists Anjali Kalpeshkumar Karia — the record is kept
single-source rather than promoted.

## Effect on the contract

`PREREGISTRATION.md` sets the minimum sample as "51 standard invitations, **or the full
verified-supply list if it is smaller**". That clause now fires: the list is **39**.

The primary metric is unaffected. `invite_accept_rate` is measured perfectly well at n=39.
What tightens is the secondary stage, which the contract already declared non-decisive:

| Invitation pool | Accept rate needed for 29 accepts | |
|---|---|---|
| 39 (any identity) | **74.4%** | implausible for a note-less cold invite |
| 26 (two-source only) | **111.5%** | impossible |

So the **PROCEED** band is unreachable on this supply, and the reply rate cannot become
decisive however the accept rate lands. That is a property of the account list, not of the
channel, and it is exactly what the ADJUST band says to fix: expand the qualified list, do
not buy a subscription, because a subscription fixes the invitation and the invitation is
not what is short.

## Method, and its ceiling

- **Name-first beats company-first.** Searching the register's name plus the company is far
  more precise than searching the company plus a role. Both wrong candidates above came from
  company-first queries.
- **LinkedIn rate-limits automated profile fetching at roughly a dozen requests** (HTTP 999).
  Direct fetch confirmed two identities before the limit and was then abandoned. No attempt
  was made to evade it, and no logged-in session was used — restricting the account this
  experiment depends on would cost more than the data is worth.
- Consequence: most records rest on a **search-engine rendering** of the profile title rather
  than the page itself. That is why nothing here is `verified`.

## The 12 with no identity

TWC IT Solutions · Secure Chain · Texaport · cyberISMS · Fortitude Cyber · Aursec · Neuways ·
Brightsolid · Air IT · System Force IT · Foresight IT Services · DSI Ltd

Two distinct causes, worth separating because they need different work:

1. **Too new or too small.** cyberISMS, Fortitude Cyber and Aursec were incorporated 2024–25.
   The register names their directors; those people do not appear on LinkedIn under that
   company.
2. **Name collision.** TWC, Foresight, DSI and System Force share their names with larger
   overseas firms that dominate every result. The person may well be findable by someone
   logged in who can search within the company page.

## Ownership changes observed in passing

Recorded because they affect qualification, not this contract: **Bluecube** now trades as "An
Ekco Company", **totality services** was sold to Lyra Technology Group, **Zenzero** took
majority investment from Macquarie Capital, and **M247**'s UK connectivity and IT arm was
acquired by Convergence Group. Each should be re-qualified before an invitation is sent.

## Not done

No invitation sent. No subscription bought. No message written. No identity resolved to a
channel beyond the profile URL itself.
