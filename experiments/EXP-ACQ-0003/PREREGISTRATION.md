# EXP-ACQ-0003 — the LinkedIn route

**Preregistered:** 2026-09-08 · **Status:** contract frozen, zero invitations sent, nothing bought

## What changed since `FEASIBILITY.md`

Two things, and both change the design rather than decorate it.

1. **Supply exists.** `EXP-ACQ-0002/REGISTER-IDENTITY-RESULT.md` returned **96 named directors
   across 34 of 51 accounts** from the statutory register, 0 fetch failures, without guessing.
   The feasibility check deferred profile research because the experiment might not be funded.
   It no longer might not be — see (2).
2. **The confound can be removed for £0.** LinkedIn Help,
   *Types of restrictions for sending invitations*, first-party:

   > "Restrictions and limits on **standard invitations** are separate from the limits placed on
   > **personalized invitations** to connect."

   The five-per-month cap that made this experiment take six months applies to invitations
   carrying a note. It does not govern a standard invitation. And a free account can message a
   1st-degree connection: *"you can only message your 1st-degree connections … for free."*

## The design that removes the confound

`FEASIBILITY.md` set the bar: *"The channel change forces a message change, which means a null
result cannot be attributed to either one. That confound has to be designed around before this is
worth running, not explained afterwards."*

It is designed around by **not putting the message in the note**:

```
rejected   invite + character-limited note carrying a shortened message
           -> channel and message both change. A null explains nothing.

adopted    standard invitation, NO note
           -> accept
           -> the EXP-ACQ-0001 message, UNCHANGED, as a direct message
           -> reply
```

The invitation becomes transport, not copy. The message under test is the same
OBSERVATION + ECONOMIC HYPOTHESIS + LOW-FRICTION CTA text that `EXP-ACQ-0001` sent, byte for
byte where the account has a teardown. A note-less invite is also **not a cheaper version of a
personalised one** — it is a weaker one, and that cost is paid in the accept rate, which is
precisely what this experiment measures.

## The primary metric is the accept rate, and the arithmetic says it has to be

The instinct is to make `meaningful_reply_rate` primary, as in `EXP-ACQ-0001` and `-0002`. At
this account count that is not available, and preregistering it would repeat `EXP-ACQ-0002`'s
exact defect — a contract frozen, then discovered to be unrunnable.

Supply ceiling: **51 non-disqualified accounts, one named buyer each → at most 51 invitations.**

| To reject | Replies stage needs | Required accept rate | Verdict |
|---|---|---|---|
| KEEP (true 10%) | 29 accepted connections | **56.9%** | possible, but only at an implausible accept rate |
| ITERATE (true 5%) | 59 accepted connections | > 100% | **impossible at any accept rate** |

At plausible accept rates the reply stage is simply under-powered:

| Accept rate | Accepts from 51 | P(0 replies given a true 10%) | Can reject KEEP? |
|---|---|---|---|
| 20% | 10 | 34.9% | no |
| 30% | 15 | 20.6% | no |
| 40% | 20 | 12.2% | no |
| 57% | 29 | 4.7% | yes |

So the reply rate is recorded but **is not this experiment's verdict**, and a null on it means
nothing. The accept rate is the genuine unknown, it has no baseline anywhere in this repo, and
n=51 measures it properly.

## Contract

| | |
|---|---|
| Primary metric | `invite_accept_rate` = accepted ÷ invitations sent |
| Route | `linkedin/named_buyer` — never merged into the email rows |
| Minimum sample | **51 standard invitations**, or the full verified-supply list if it is smaller |
| Secondary metric | `meaningful_reply_rate` on accepted connections — **reported, never decisive** |
| Cost | **£0.** Free tier. No subscription is bought under this contract |

### Decision rule on the primary metric

Each boundary is derived, not chosen.

| Observed accept rate | Reading | Decision |
|---|---|---|
| **≥ 56.9%** | 29+ accepts: the reply stage can reject KEEP | **PROCEED** — run the reply stage as preregistered here |
| **19.3% – 56.8%** | The channel works; the binding constraint is the number of accounts, not the invitation | **ADJUST** — expand the qualified list. Do not buy a subscription: it fixes the wrong step |
| **< 19.3%** | Even tripling the list to 150 accounts cannot reach 29 accepts | **PIVOT** — the invitation itself is the constraint. A personalised note is the thing to test, that requires Premium, and it is `EXP-ACQ-0004`, not a rescue of this one |
| **0 of 51** | Wilson 95% CI 0 – 7.0% | Route closed for this ICP, on the same evidential footing as the email wedge |

19.3% is 29 ÷ 150 — the accept rate below which a threefold expansion of the account list still
cannot power the reply stage. 56.9% is 29 ÷ 51.

## The spend decision this contract settles

**It defers it, on purpose, and names what would trigger it.**

`FEASIBILITY.md` framed the choice as Sales Navigator Core at US$119.99/mo versus Premium, and
recommended pricing Premium first. This contract says: **buy neither yet.** The paid tiers exist
to unlock personalised connection notes and InMail. Nothing here needs InMail, and whether a
personalised note is worth paying for is exactly what an accept rate measured without one tells
you — for £0, before the money moves.

A subscription becomes the right purchase only on the **PIVOT** branch, and then it is bought to
run a specific comparison (note versus no note) rather than to make this experiment work.

The same logic applies to Gojiberry AI at US$99/mo, which surfaced on 2026-09-08 as a cheaper
route to the same capability. Its API and MCP access are Pro-plan gated — two freshly minted keys
returned `401` on every route, identically to no key at all — so it is a purchase, not an
integration, and it belongs on the same PIVOT branch under the same rule. It is not preregistered
here.

## Admission rule

An invitation counts toward the minimum sample only if **all** hold:

1. The recipient is a **named individual**, not a company page.
2. Their commercial decision-making role is evidenced on their own LinkedIn profile — the
   statutory register publishes the office ("Director") and never the function, so a register
   appointment alone does **not** admit an account.
3. The account is not `disqualified*` and is not suppressed.
4. **One invitation per account.** A second director at the same company is a second touch at one
   account, not a second observation, and would inflate n against a supply ceiling this contract
   is built on.
5. The invitation carried **no note**. One that did belongs to `EXP-ACQ-0004`.

Failing (2) excludes the account rather than downgrading it — the lesson `EXP-ACQ-0002` paid for.

## What n=51 can and cannot decide

It measures the accept rate to roughly ±12 points at mid-range (Wilson 95%: 15/51 = 29.4%,
CI 18.7 – 43.0%). That is enough to separate the three decision bands above and not much more.
It cannot decide the reply rate. Stated here so nobody reads the outcome as more than it is.

## Known unknowns, recorded as unverified

- **LinkedIn does not publish invitation limits.** *"LinkedIn Support cannot disclose the type or
  reason for the restriction."* A restriction, if hit, lasts about one week. Widely-quoted weekly
  caps come from automation vendors selling tools to exceed them and are **not relied on**;
  the same class of source failed verification in `EXP-ACQ-0002`.
- Pace invitations so a restriction is not the thing that ends the sample. If one lands, it is
  recorded as an execution event, not as a rejection by the market.
- **An accepted connection is a warmer population than a cold inbox.** `accept → reply` is
  therefore not the same quantity as `EXP-ACQ-0001`'s `send → reply`, even though the message is
  identical. This is why the reply rate is reported and not compared.

## What this does not authorise

No invitations. No subscription. No message sent. Invitations and messages are external contact
and money is a spend decision; both are proposed and stopped, per the standing rule. The next
internal step is verifying LinkedIn profiles for the 34 register-resolved accounts and the 17
unresolved ones, which is research and needs nobody's permission.
