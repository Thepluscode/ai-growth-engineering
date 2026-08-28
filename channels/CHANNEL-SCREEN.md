# Untried channel screen — 2026-08-28

Distribution is the measured constraint. Three independent readings say so: shared-inbox email
0/48, the personal email route unreachable without paying, and the owned site at ~47 visitors a
month with every referrer empty.

This screens the channels that have never been tried. The criteria are fixed here before any
channel is assessed, for the same reason `DISCOVERY-PROTOCOL.md` was: criteria written afterwards
get written to fit the answer someone already wants.

## Criteria

| # | Test | Why it is a gate and not a preference |
|---|---|---|
| 1 | **Audience verifiably present** | `EXP-ACQ-0002` was preregistered and then found unrunnable. Reachability is checked first now, always |
| 2 | **Costs nothing to reach first signal** | Two spend decisions are already open and unanswered. A third would just queue |
| 3 | **Metric readable with what we have** | `contact_intent` is a **custom event** and returns 402 on the `hobby` plan. Any channel whose success is an on-site conversion is unmeasurable today, whatever it does to traffic |
| 4 | **Not already measured empty** | 0/48 is an answer, not an invitation to resend |

Criterion 3 is the one that reorders everything. Visitor counts are free through
`/v1/query/web-analytics/visits/*`; conversions are not. A channel that drives traffic to a site
whose conversion event cannot be counted produces a number nobody can act on.

## The screen

| Channel | Audience present | Free to first signal | Metric readable | Verdict |
|---|---|---|---|---|
| **Social — LinkedIn organic** | **Yes, observed** | **Yes** | **Yes, LinkedIn's own free analytics** | **Candidate** |
| Organic search | Unverified — see below | Yes | Traffic only, not conversion | Blocked on measurement |
| Content | Same audience problem as search | Yes | Traffic only | Follows search |
| Partners / affiliates | Plausible — the 55 MSPs could be partners rather than prospects | Yes | Replies, in `outreach.csv` | Second candidate, same reachability risk |
| Email / lifecycle | **No list exists** | Yes | n/a | Dead until an audience exists |
| Paid media | Buyable | **No** | Conversion unreadable on `hobby` | Blocked twice over |

## Organic search is not a channel yet

Two exact-phrase searches — the site's own `<title>` string, and the domain plus its positioning
line — returned nothing from `theplus-tech.com`. `robots.txt` and `sitemap.xml` both serve 200 and
the sitemap is well-formed, so this is not a crawlability defect; the domain is 15 days old.

Stated with its limit: the search tool available here is US-only and is not necessarily Google's
index, and a `site:` query was silently ignored rather than honoured, so "two searches found
nothing" is **not** proof of non-indexation. The authoritative check is **Google Search Console,
which is not connected**. Connecting it is free, is an account action rather than a code change,
and is the only way this channel gets a denominator. Until then organic search has no measurement
at all — worse than the site, which at least has visitor counts.

The sitemap's `lastmod` is still `2026-08-13` across every URL while the site has changed since.
Minor, and worth fixing whenever the site is next touched.

## Why LinkedIn organic, specifically

It is the only channel where **the buyers were actually observed**. `EXP-ACQ-0002`'s discovery
found named commercial decision-makers with public profiles at 10 of 10 accounts checked, while
finding zero published email addresses. That is a direct, evidence-backed answer to criterion 1,
and no other untried channel has one.

It is also free, and the distinction matters because the LinkedIn feasibility work reached the
opposite conclusion about a *different* mechanism. What costs money is **personalised connection
notes**, capped at five a month on a free account. **Posting is not capped that way.** Organic
publishing, profile visibility and inbound replies do not require Premium, so `EXP-ACQ-0003`'s
spend decision does not block this.

Its metric is readable without Vercel Pro, because success is measured on LinkedIn — impressions,
profile views, and inbound conversations — not as an on-site conversion.

## Honest risks

- **Not the same as the outbound test.** Publishing does not target the 55 accounts. It reaches
  whoever the feed reaches, which may not be the ICP at all. First job is to measure who actually
  turns up, not to assume.
- **Slow.** No single post is a result. This needs weeks of cadence before any denominator exists,
  and a preregistration written now would be inventing thresholds with no baseline — the exact
  error `EXP-CREATIVE-0001` was blocked for.
- **Founder-time, not agent-time.** The cost is not money, it is a person writing in their own
  voice repeatedly. That is the constraint to be honest about rather than the subscription.
- **It has an existing corpus.** `/insights` already holds written material. That lowers the cost
  of starting but does not change the audience question.

## Recommendation

1. **Run LinkedIn organic as a measurement period, not an experiment** — the same shape as the
   owned-site baseline window, and for the same reason: there is no baseline, so there is nothing
   to preregister against. Establish impressions, profile views and inbound per post before any
   threshold is written down.
2. **Connect Google Search Console.** Free, one account action, and it is the only thing that turns
   organic search from unmeasurable into measurable.
3. **Do not buy anything yet.** Both open spend decisions — LinkedIn Premium and Vercel Pro — stay
   open. Neither is worth paying for while the question is whether anyone arrives at all.

Nothing is published, posted or preregistered by this document. Publishing is external surface: it
is proposed and it stops here.
