# Owned-Site Baseline — measurement period, not an experiment

**Opened:** 2026-08-21 · **Closes:** 2026-09-18 (4 weeks) · **Surface:** theplus-tech.com

`EXP-CREATIVE-0001` was requested and could not be preregistered. Not because the machinery is
missing — the trust gate, the integrity gate and the experiment contract are all built and tested —
but because **there is no baseline**, and a preregistered threshold invented without one is the
failure the freeze rule exists to prevent.

This is deliberately **not** an experiment. Nothing changes on the site during the window. It has no
hypothesis, no variant and no verdict, so it gets no `EXP-` id.

## What is being established

| Figure | Why it is needed |
|---|---|
| Sessions per week | The denominator. Without it no rate means anything |
| `contact_intent` events per week | The conversion numerator |
| `contact_intent` per 1,000 sessions | The primary metric's real starting value |
| Split by `path` property | Whether assessment, briefing, pilot and subscription differ |
| Traffic source, if Vercel reports it | Which channel, if any, is actually delivering anyone |

The `path` split matters: the site runs six CTAs against four offers, so a single blended rate would
hide which of them anyone actually wants.

## Why four weeks

Shorter risks a week-shaped artefact — a single post, a single referral, a quiet fortnight — becoming
the baseline every future threshold is measured against. Longer delays everything downstream for
precision the decision does not need.

## What this window decides

Whether the site can carry an A/B at all. Sessions needed per arm for a two-proportion test at 80%
power, 5% two-sided:

| baseline rate | target | total sessions both arms |
|---|---|---|
| 1% | 1.5% | 15,500 |
| 1% | 2.0% | 4,638 |
| 2% | 3.0% | 7,652 |
| 2% | 4.0% | 2,282 |
| 5% | 7.5% | 2,942 |
| 5% | 10.0% | 870 |

At the end of the window, weekly sessions × the horizon you are willing to run gives the answer
directly. If four weeks of traffic is not within an order of magnitude of the smallest cell,
`EXP-CREATIVE-0001` is not runnable on this surface and the constraint is audience, not creative.
Say that plainly rather than running an underpowered test and reading noise as a result.

## The reading to take now

From the Vercel dashboard → Analytics, for the clean period **since 2026-08-22** (see "The window's
real start" below — anything earlier is contaminated):

```
sessions
contact_intent events
contact_intent by path
top referrers
```

Record it as evidence with `age`-style provenance rather than pasting a percentage:

```
numerator   = contact_intent events
denominator = sessions
```

Never store the rendered rate. A rate cannot be recomputed, pooled across weeks, or audited.

## What happens at close

1. Compute `contact_intent per 1,000 sessions` from the pooled numerator and denominator.
2. Set `EXP-CREATIVE-0001`'s success and review thresholds from that figure — not from a number
   anyone would like to see.
3. Declare its trust guardrails. On an anonymous site with no subscription and no transaction, most
   of `CHANNEL_GUARDRAILS["landing_page"]` will be `required=False` with a reason recorded, which is
   the honest reading, not a loophole.
4. Preregister. From that point the contract is frozen.

## First reading — 2026-08-21, ~24 hours in

```
sessions            47
contact_intent       3
rate              6.4%   95% CI (Wilson) 2.2% - 17.2%
```

**Traffic exists.** I predicted a near-zero denominator and was wrong. At 47/day the site sees
roughly 1,300 sessions a month, which puts a two-arm test inside 2-7 weeks depending on the effect
size worth detecting.

**The reading is contaminated and must not become the baseline.** At least one of the three events is
our own click while verifying the instrumentation on 2026-08-20, and our sessions sit in the
denominator. What that does to the number:

| | rate | 95% CI |
|---|---|---|
| as reported | 3/47 = 6.4% | 2.2% - 17.2% |
| minus 1 self-click | 2/46 = 4.3% | 1.2% - 14.5% |
| minus 2 self-clicks | 1/45 = 2.2% | 0.4% - 11.6% |

A threshold set anywhere in that spread would be set on our own behaviour. The interval also spans
an order of magnitude, so even uncontaminated, n=47 cannot fix a threshold.

Recorded as `EV-BASELINE-01` at confidence 0.6 — an order-of-magnitude signal that traffic exists,
not a baseline rate.

## Fixes — closed 2026-08-27

1. **Exclude internal traffic — DONE and live.** `theplus-tech-website@79513d2`, "Stop measuring
   ourselves", committed 2026-08-22 06:42 BST. `?internal=1` sets a per-browser `localStorage` flag;
   `?internal=0` clears it. Pageviews and custom events are dropped **together** via
   `beforeSendEvent`, because Vercel pageviews cannot carry custom properties while custom events
   can — tagging the numerator against an untaggable denominator would leave events with no matching
   sessions, which reads as a funnel bug rather than as internal traffic. Storage failures fail
   **open**: a visitor in private browsing is measured rather than silently dropped.

   Verified against the origin, not the branch:

   ```
   $ curl -s https://theplus-tech.com/ | grep -oE '/_next/static/[A-Za-z0-9_./-]+\.js' | sort -u
   ... 8 chunks ...
   $ grep -l tpt_internal_traffic js/*
   js/__next_static_immutable_chunks_10xfhec6y72xf.js
   ```

   `tpt_internal_traffic` and `contact_intent` are both present in the bundle production serves as of
   2026-08-27. A merged commit is not a deployed one; this is the deployed one.

2. **Never verify instrumentation against production.** Standing rule, no artefact to close.

3. **`path` split — DONE.** Every `contact_intent` carries `path` (from the mailto subject) and
   `label`. One delegated listener on `a[href^="mailto:"]` rather than per-anchor handlers, so a CTA
   added later cannot silently go unmeasured.

## The window's real start

The exclusion went live on 2026-08-22, not on 2026-08-21 when the window opened. Vercel has no
retroactive filter, so the 20th-to-22nd traffic is a mixture and cannot be separated at read time.

**The clean window is 2026-08-22 to 2026-09-18.** `EV-BASELINE-01` stays on the record at confidence
0.6 as an order-of-magnitude signal that traffic exists; it is not a baseline and no threshold may be
derived from it. The pooled numerator and denominator for the baseline are taken from 2026-08-22
onward only.

## Closed early — 2026-08-28

The window was opened for four weeks. It closed after one, because the reading is decisive and
holding it open would only make a settled answer later.

Read from Vercel's own API through the authenticated CLI (`vercel api /v1/query/web-analytics/...`),
not from the dashboard. Every figure below is the API's echoed window, not the one requested — the
endpoint silently clamps `from`/`to` and only honours `since`/`until`, and the first call came back
answering a window nine days wider than it was asked for.

### Daily series, the entire life of the measurement

Web Analytics was enabled 2026-08-20 11:25 BST. There is no earlier data to have.

```
2026-08-20   15 visitors   26 pageviews     <- instrumentation verified against production
2026-08-21    9            10
2026-08-22    6             9               <- internal-traffic exclusion goes live
2026-08-23    0             0
2026-08-24    2             2
2026-08-25    2             2
2026-08-26    0             0
2026-08-27    0             0
2026-08-28    1             1
             --           ---
all time     35            50
clean window 11            14               (2026-08-22 onward)
```

Referrers: **one row, empty hostname, all 35 visitors.** Nothing is referring anyone. Paths: `/` 34
visitors, `/insights` 1, `/privacy` 1.

### `EV-BASELINE-01` was wrong, and by an order of magnitude

It recorded *"47 sessions, 3 contact_intent events, ~24 hours in"* and concluded traffic exists at
roughly 1,300 sessions a month. The API cannot reproduce that. As of 2026-08-21 the cumulative
totals were **24 visitors and 36 pageviews**, and no single day ever reached 47 of anything. The
figure survives no window and no metric.

Checked before saying so: dropping the `environment` filter changes nothing — grouping by
environment returns a single `production` row with the same 35 and 50 — so it is not preview
traffic hidden by a filter. `requestPath` `/` now shows exactly 47 *cumulative pageviews*, which is
a suggestive coincidence and is **not** asserted as the cause; on 2026-08-21 that cumulative was 36.

The honest reading: **1.6 visitors a day, about 47 a month.** The original prediction in this
document was a near-zero denominator, retracted on 2026-08-21 with "I predicted a near-zero
denominator and was wrong". It was not wrong. A misread number overturned a correct prediction,
which is worse than having no reading at all.

### The numerator cannot be read on this plan

```
$ vercel api /v1/query/web-analytics/events/count?...
Error: Accessing Analytics custom events requires an Enterprise or Pro plan. (402)
```

The team is on `hobby`. `contact_intent` is a **custom event**, so the conversion numerator is
behind a paywall. The three events in `EV-BASELINE-01` cannot be re-verified, and no future
`contact_intent` count can be obtained either without upgrading.

So the window was never going to produce a baseline: its denominator is 30x smaller than recorded
and its numerator is unreadable.

### The site cannot carry an A/B test

At 11 visitors a week, against the power table above:

| baseline -> target | sessions both arms | time to fill |
|---|---|---|
| 5% -> 10% | 870 | **1.5 years** |
| 2% -> 4% | 2,282 | 4.0 years |
| 5% -> 7.5% | 2,942 | 5.1 years |
| 1% -> 2% | 4,638 | 8.1 years |
| 2% -> 3% | 7,652 | 13.4 years |
| 1% -> 1.5% | 15,500 | 27.1 years |

The most generous cell in the table takes eighteen months.

### Verdict

**`EXP-CREATIVE-0001` is not runnable on this surface, and the constraint is audience, not
creative.** This is what the document said to say if four weeks came back an order of magnitude
short. It came back two orders short in one.

No creative experiment is preregistered. The site does not need a better hero; it needs anyone at
all to arrive, and with every referrer empty there is currently no channel pointing at it. That is
the work — and it is the same finding the outbound track reached from the other direction:
`EXP-ACQ-0001` closed the shared-inbox route at 0/48, `EXP-ACQ-0002` found the personal route
unreachable, and the owned surface has no audience to test on. **Distribution is the constraint
across every channel measured so far.** Nothing in the creative, offer or messaging layer is
falsified by this; none of it has been given a sample.

## Standing risk

The window may still return too little to test on. But the first reading says the constraint is
likelier to be *effect size* than audience: at 6.4% a doubling resolves in two weeks, while a 50%
lift needs seven. Choose the hypothesis to match what the traffic can actually resolve, rather than
picking the effect first and discovering later it was never detectable.
