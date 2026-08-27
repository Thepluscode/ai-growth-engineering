# Contact discovery — the rule, fixed before the searching starts

`EXP-ACQ-0002` needs **30 delivered sends to a named buyer's own mailbox**. This document
decides what counts as reachable, and it is written *before* any account is researched. If the
bar is set after the count is known it will be set to whatever produces 30, which is how
`EXP-ACQ-0001` ended up reporting 50 qualified sends of which 48 went to a shared inbox.

## The question

Not "can 30 buyers be named" — the teardowns already name many. It is **"can 30 named buyers be
reached on a person-specific route"**. Those are different, and only the second one gates the
experiment.

## Classification

| Class | Requires | Counts toward 30 |
|---|---|---|
| `reachable_email` | A personal mailbox for a named commercial decision-maker, **observed** on a citable public source | **Yes** |
| `reachable_linkedin` | A named decision-maker with a findable LinkedIn profile, no personal mailbox | **No** — see below |
| `pattern_only` | Name known; the domain's format is inferrable but no personal address was observed | **No** |
| `name_only` | Person named; no person-specific route found | No |
| `none` | No named commercial decision-maker found | No |

A "personal mailbox" is one addressed to a person: `firstname@`, `f.lastname@`,
`firstname.lastname@`. `info@`, `sales@`, `hello@`, `enquiries@`, `contact@`, `support@` are
`role_inbox` and were already tested at 0/48.

## Why `pattern_only` does not count

Five of `EXP-ACQ-0001`'s sends were lost to guessed or placeholder addresses, and four hard
bounced. An inferred address is a hypothesis about a mail server, not a contact. It may be
promoted to `reachable_email` only by observing a *confirmed* address on the same domain in the
same format — the pattern needs a witness, not a plausible shape.

## Why LinkedIn is recorded but excluded

A LinkedIn profile is a real person-specific route, and finding one is worth recording. It is a
**different channel** from email, with its own delivery rates, its own norms and its own cost.
Mixing it into the same sample is the error the `recipient_class` column was just built to
prevent. If email cannot reach 30, LinkedIn becomes its own preregistration, not a substitute
population inside this one.

## The decision this produces

- **>= 30 `reachable_email`** — `EXP-ACQ-0002` runs as preregistered.
- **< 30** — it does not start. The finding is then about the ICP, not the message: mid-market
  UK MSPs do not publish their commercial decision-makers' addresses, and cold email is
  structurally a shared-inbox channel for this segment. That is a real result and it is recorded
  as one, not worked around by relaxing the definition.

## Sources permitted

Company website (team, leadership, contact pages), press releases, Companies House filings,
conference speaker listings, published PDFs, industry directories, LinkedIn public profiles.
Every classification records the URL it came from. No purchased list, no enrichment API, no
guessing.
