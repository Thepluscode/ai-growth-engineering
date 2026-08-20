# Batch 06 — Replacement Messages (DRAFT, NOT SENT)

Status: **drafted 2026-08-20 for review. Nothing sent. No Gmail draft created.**

These five replace the four accounts retired as `disqualified_unreachable_by_email` plus one, to
restore the delivered sample toward the 50-send minimum. Every recipient address was verified on the
company's own contact page on 2026-08-20 as published, non-obfuscated, and not a support queue.

Every observation below was read off the company's live site today. Nothing is inferred from a
directory, a summary, or a previous batch.

---

## 1. AMVIA — `hello@amvia.co.uk`

**Subject:** For commercial owner: assessment handoff experiment

I noticed AMVIA's free security assessment is unusually concrete — 20 minutes, gaps prioritised, a
remediation roadmap, and a reply within two hours — but the CTA hands the visitor to a Typeform on a
different domain at the exact moment they commit.

I'd test whether asking the first two questions on your own page before that handoff improves
*completed* assessments rather than started ones.

I mapped the handoff experiment in a one-page teardown. Want me to send it?

> **Observed:** homepage CTA "Get Your Free Assessment"; cyber page CTA "Get My Free Security Audit";
> both resolve to `form.typeform.com/to/jkSHfmE1`. The same offer is also named two different ways.

---

## 2. Utilize — `info@utilize.co.uk`

**Subject:** For commercial owner: competing free-offer experiment

I noticed Utilize offers both "Book a free consultation" and "Book your free audit" on the same page
with no stated difference between them, alongside "Get started" and "Discover ASCEND".

I'd test whether naming one as the default first step raises qualified bookings, rather than splitting
the same intent four ways.

I mapped the single-CTA experiment in a one-page teardown. Want me to send it?

> **Observed:** four distinct entry CTAs on the homepage; two of them free offers with no
> differentiating copy.

---

## 3. Grant McGregor — `info@grantmcgregor.co.uk`

**Subject:** For commercial owner: entry-offer experiment

I noticed your contact page is explicit that the form isn't monitored for support, which keeps the
commercial route clean — but the only entry action on the site is "Start a Conversation", repeated
four times, with no bounded first step for a buyer who isn't ready to talk yet.

I'd test whether one named, scoped assessment produces more qualified conversations than adding
traffic to the same conversation CTA.

I mapped the entry-offer experiment in a one-page teardown. Want me to send it?

> **Observed:** no free assessment, audit or scorecard anywhere on the homepage; "Start a
> Conversation" x4 and "Explore Services" x3.

---

## 4. Wanstor — `sales@wanstor.com`

**Subject:** For commercial owner: review-output experiment

I noticed the 30-minute Experience Review is a genuinely bounded first step with a benchmark attached
— but it competes on the same page with "Fix your service experience", "Secure your estate" and
"Explore your AI Roadmap", three destinations phrased like offers.

I'd test whether naming what the review actually hands back improves booked reviews from the same
traffic.

I mapped the one-line experiment in a one-page teardown. Want me to send it?

> **Observed:** "Book a 30-minute Experience Review" benchmarks technology against industry standards;
> three outcome-phrased CTAs compete with it on the homepage.

---

## 5. Nviron — `hello@nviron.co.uk`

**Subject:** For commercial owner: single-entry experiment

I noticed Nviron routes every visitor to the same action under three different labels — "Schedule a
call", "Talk to an expert" and "Get in touch" — with no lower-commitment step for someone still
diagnosing the problem.

I'd test whether a single named first step earns more qualified conversations than three phrasings of
the same request.

I mapped the smallest clean test in a one-page teardown. Want me to send it?

> **Observed:** no free assessment or audit on the homepage; three separate labels for one contact
> action.

---

## Before any of these are sent

- [ ] Suppression check against the registry for all five addresses
- [ ] Duplicate check — none of these five appears in `outreach.csv`
- [ ] Explicit approval; `bulk_outreach` is `require_approval` under `policies/growth_action_policy.json`
- [ ] After sending: confirm the Gmail SENT label and message id per send, then add one `outreach.csv`
      row each with `stage=sent_awaiting_reply`
- [ ] Watch for bounces for 24h and mark any `stage=bounced` so the denominator stays honest

Two of the five (Grant McGregor, Nviron) share the same underlying leak — no bounded entry offer.
That is a real pattern in this ICP, not a copy shortcut: each message cites that company's own
observed CTAs, and neither claims anything the other's site shows.
