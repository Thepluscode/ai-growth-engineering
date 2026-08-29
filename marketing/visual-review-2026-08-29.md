# Visual review of the shipped site — 2026-08-29

The redesign was verified on 2026-08-28 by HTTP status and byte count. Nobody had looked at it.
This is the look, done in a real browser engine at 1440 and 390, and it found two things no status
code could.

Run with `?internal=1` first, so the review does not contaminate the measurement it was built to
protect. That also tested the exclusion end to end for the first time:

```
localStorage tpt_internal_traffic = "1"
console: [analytics] internal traffic exclusion: ON
```

## What is fine

- **Desktop.** Dark editorial, one type system, gold accent used sparingly. It reads as a considered
  publication rather than a template, and the evidence blocks carry their own `MEASURED` /
  `BUILT, NOT MEASURED` / `NOT PROVEN` labels, which is the doctrine showing through in the design.
- **390px.** `scrollWidth - clientWidth = 0` on the homepage and on the sprint page. Single column,
  masthead wraps rather than toggling, the evidence tables stay inside their containers. The
  tracker's outstanding "verify on a physical device" is now at least verified in a real engine.
- **Routes.** `/`, `/workflow-audit`, `/workflow-audit/sample-report`, `/insights`, `/privacy` all
  200; `/nope` 404s. The only console error in the session was my own probe of `/nope`.

## Finding 1 — the site sells two different products at one price

A buyer clicks **"Rescue Sprint £1,500"** on the homepage and lands on a page whose deliverables do
not overlap with what the homepage just promised. Extracted from the DOM of both pages, not read off
a screenshot:

| Deliverable | Homepage | `/workflow-audit` |
|---|---|---|
| Workflow and evidence-source map | yes | — |
| Reusable answer bank | yes | — |
| Missing-controls report | yes | — |
| Exportable response pack | yes | — |
| 30-day automation roadmap | yes | — |
| Workflow map | — | yes |
| Opportunity register | — | yes |
| Risk and compliance flags | — | yes |
| ROI estimate | — | yes |
| 30-day build roadmap | — | yes |

**Ten labels. Five each side. Zero shared.**

The naming is three-way inconsistent in the same click path:

```
homepage H2      Security Questionnaire Rescue Sprint
page <title>     AI Workflow Opportunity Audit · ThePlus Tech
page H1          Find the workflow worth automating.
URL              /workflow-audit
page body        "If the audit cannot find..."   "The audit defines data boundaries..."
page buttons     "Start a sprint  £1,500"
```

The page calls itself an *audit* in its title and prose and a *sprint* in its buttons, while the
homepage calls it a *Rescue Sprint*. The framing differs too: the homepage sells relief from security
questionnaires, the page sells finding a workflow worth automating. Those may be the same engagement
— but a buyer cannot tell, and this is the only page describing the paid offer.

Scored with the repo's own instrument rather than by opinion:

```
$ CongruenceScore(audience=4, problem=2, message=1, visual=5, offer=0, cta=4)
total    16 / 30
decision DO_NOT_SPEND
```

`visual_match` is a 5 and `offer_match` is a 0, which is the whole story: it looks like one product
and describes two.

**`DO_NOT_SPEND` independently confirms the channel screen's block on paid media**, by a completely
different route. The screen blocked paid because it costs money and its conversion event is
paywalled. This blocks it because the page a click lands on contradicts the click.

**Not fixed here.** Which offer is real — questionnaire rescue or automation audit — is a positioning
decision, and rewriting it would be inventing the answer rather than surfacing the conflict.

## Finding 2 — the confidential-enquiries address is a Gmail account

Every call to action on both pages resolves to one `mailto:`:

```
mailto:ogievatheophilus@gmail.com
```

The sprint page's footer reads *"Confidential enquiries to ogievatheophilus@gmail.com"*. The offer is
evidence, compliance and security posture, sold to regulated buyers; the word *confidential* sitting
next to a personal Gmail address undercuts the argument before the page is read. This was already
open question 2 in the website tracker; seeing it in place makes it worse than it reads as a note.

Worth knowing: the domain already runs **Google Workspace** — `v=spf1 include:_spf.google.com` on
`theplus-tech.com`, found while checking Search Console verification. A domain mailbox is therefore
likely already available or one console action away, which makes this cheap to fix rather than a
project.

## What this does not cover

Typography at real reading distance, colour on a calibrated display, and how the page feels to
someone who is not looking for defects. A rendering engine at two widths is not a person's eye, and
the design system stays `DEPLOYED` rather than `VERIFIED` until someone looks.
