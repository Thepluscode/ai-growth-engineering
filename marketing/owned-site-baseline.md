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

From the Vercel dashboard → Analytics, for the period since 2026-08-20:

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

## Fix before the window continues

1. **Exclude internal traffic.** Until then every verification click inflates the numerator, and the
   effect is largest exactly when the sample is smallest. Vercel Analytics has no IP filter, so the
   options are a `localStorage` opt-out flag checked in `FunnelTracking`, or tagging internal
   sessions with a property and filtering at read time. The second keeps the raw data intact.
2. **Never verify instrumentation against production again.** Use a preview deployment. The check
   that proves the event fires is the same action that corrupts the measurement.
3. **Get the `path` split.** Six CTAs against four offers; a blended rate hides which offer anyone
   wants, and that is the more useful number.

## Standing risk

The window may still return too little to test on. But the first reading says the constraint is
likelier to be *effect size* than audience: at 6.4% a doubling resolves in two weeks, while a 50%
lift needs seven. Choose the hypothesis to match what the traffic can actually resolve, rather than
picking the effect first and discovering later it was never detectable.
