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

## Standing risk

Four weeks of a near-zero denominator is itself the finding. If it arrives, the next move is not a
better hook — it is building an audience, and no amount of persuasion engineering substitutes for
having someone to persuade.
