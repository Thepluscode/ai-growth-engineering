# Statutory register — identity supply

**Run:** 2026-09-08 · **Source:** Companies House public officers pages · **Connector:**
`officer_signal_connector`

`DISCOVERY-RESULT.md` closed the email route: 18 accounts, **0** published personal
mailboxes for a named commercial decision-maker. This run asks the neighbouring
question — not *can we email them*, but *do we know who they are* — against the one
source obliged by statute to publish it.

## Answer

**Yes. 96 named directors across 34 of the 51 non-disqualified accounts.** Every one is
a current officer of record, read from the register, with a statutory role, an
appointment date and the register's own stable officer id.

| | |
|---|---|
| Non-disqualified prospects | 51 |
| Resolved to a company number **without guessing** | **34** |
| Ambiguous (more than one live exact match) | 0 |
| No live exact name match | 17 |
| Register pages fetched | 34 |
| Fetch failures | **0** |
| Companies returning at least one current director | **34 of 34** |
| **Named directors** | **96** (mean 2.8 per company) |

## What is and is not established

An **identity**, not an address, and not intent. The register publishes the statutory
office — "Director" — never the commercial function, so which of a company's 2.8
directors owns the revenue decision is unknown from this source. No email address is
published and none was inferred. `DISCOVERY-RESULT.md` stands unchanged: the email
route is still closed.

What changes is the **input to a route that needs a name rather than a mailbox.**
`EXP-ACQ-0003` was blocked on a spend decision with no evidence that there would be
anyone to point a subscription at. There are 96 people, at 34 accounts, obtained
without guessing.

## Resolution rule

Accepted only where **exactly one live search result carried the prospect's name after
stripping legal form** (`limited`, `ltd`, `plc`, `llp`, `lp`) and nothing else.

An earlier pass also stripped `group`, `holdings`, `uk` and `co`. It reported 34
resolved and 5 ambiguous — but it had matched *Slink* to `SLINK GROUP LIMITED` and
*Air IT* to `AIR IT GROUP LIMITED`, which are separate legal entities that can carry
separate boards, while collapsing genuinely distinct companies into false ambiguity.
Tightening the rule **raised** clean resolution (5 ambiguous → 0) and dropped the
guesses. A match on a company's *previous* name is not a match.

The 17 unresolved are unresolved, not absent: most publish under a name that differs
from their trading name. They need a person to look them up, and a wrong number
attributes a director to the wrong company.

## As a recency signal, the answer is zero

The connector gates on recency, because an appointment years old is not a change. Over
the same 34 accounts:

| Window | Directors appointed | Companies |
|---|---|---|
| 90 days | **0** | 0 |
| 180 days | 2 | 2 |
| 365 days | 8 | 8 |
| 730 days | 12 | 10 |

`age sweep-sources --max-age-days 90` returned **0 candidates and recorded 0 signals**,
which is the honest reading: boards at mid-market UK MSPs do not change often. The
window was **not** widened to produce a number. Opening it to 365 days would surface 8
candidates for review, and that is a decision to take deliberately, not a default.

## Guard against the reading that 0 is a broken parser

The same pages, the same parser, an unbounded window: **96 directors parsed, 0 fetch
failures, every one of 34 companies returning at least one.** A page reading
`2 officers / 1 resignation` returned exactly 1 candidate. "No recent appointments" is
therefore a measurement of the market, not a silent failure of the code.

## Not done

No candidate reviewed. No signal recorded. No identity resolved to a channel. No
contact made.

## Personal data

The 96 names are **not committed**. They exist only in the local `.age/` store, which
is gitignored; this repository is public, and a public register does not make a
publishable prospect list. Only aggregate counts appear here.
