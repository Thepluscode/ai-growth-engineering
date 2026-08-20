# Batch 06 — Replacement Messages (SENT 2026-08-20)

Status: **all six sent 2026-08-20 after explicit approval. Five delivered, one bounced.**
Each message id below was confirmed under the Gmail SENT label and the inbox checked for bounces.

These five replace the four accounts retired as `disqualified_unreachable_by_email` plus one, to
restore the delivered sample toward the 50-send minimum. Every recipient address was verified on the
company's own contact page on 2026-08-20 as published, non-obfuscated, and not a support queue.

Every observation below was read off the company's live site today. Nothing is inferred from a
directory, a summary, or a previous batch.

---

## 1. AMVIA — `hello@amvia.co.uk` — BOUNCED, id `1a01f198f5e7332f`

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

## 2. Utilize — `info@utilize.co.uk` — SENT, id `1a01f19decba01f4`

**Subject:** For commercial owner: competing free-offer experiment

I noticed Utilize offers both "Book a free consultation" and "Book your free audit" on the same page
with no stated difference between them, alongside "Get started" and "Discover ASCEND".

I'd test whether naming one as the default first step raises qualified bookings, rather than splitting
the same intent four ways.

I mapped the single-CTA experiment in a one-page teardown. Want me to send it?

> **Observed:** four distinct entry CTAs on the homepage; two of them free offers with no
> differentiating copy.

---

## 3. Grant McGregor — `info@grantmcgregor.co.uk` — SENT, id `1a01f1a16b7cbe71`

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

## 4. Wanstor — `sales@wanstor.com` — SENT, id `1a01f1a611fd0721`

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

## 5. Nviron — `hello@nviron.co.uk` — SENT, id `1a01f1c15152f11e`

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

## Pre-send checks (all completed before sending)

- [x] Suppression check against the registry for all five addresses
- [x] Duplicate check — none of these five appears in `outreach.csv`
- [x] Explicit approval; `bulk_outreach` is `require_approval` under `policies/growth_action_policy.json`
- [x] After sending: confirm the Gmail SENT label and message id per send, then add one `outreach.csv`
      row each with `stage=sent_awaiting_reply`
- [x] Watch for bounces for 24h and mark any `stage=bounced` so the denominator stays honest

Two of the five (Grant McGregor, Nviron) share the same underlying leak — no bounded entry offer.
That is a real pattern in this ICP, not a copy shortcut: each message cites that company's own
observed CTAs, and neither claims anything the other's site shows.

---

## 6. Cheeky Munkey — `info@cheekymunkey.co.uk` — SENT 2026-08-20, id `1a01f20cdecad00d`

**Subject:** For commercial owner: gated audit experiment

I noticed your strongest entry offer — a free security audit you describe as worth up to £2,000 — is
only reachable through the refer-a-friend route near the footer, while every primary CTA on the site
is "Book FREE Consultation".

I'd test whether offering that audit directly to non-referred visitors produces more qualified starts
than the generic consultation does, since it is the more specific promise of the two.

I mapped the experiment in a one-page teardown. Want me to send it?

> **Observed:** free security audit "worth up to £2,000" available only to referred new clients, in
> the refer-a-friend block near the footer; "Book FREE Consultation" is the site-wide primary CTA.
> **Reachability signals:** `info@` published as sales with a separate `help@`/`support@`; MX on
> Microsoft 365. Neither proves the mailbox exists — see EV-ACQ-REACH-02 — but no bounce in an hour.

## Batch 06 outcome

Sent 6 · delivered 5 · bounced 1 (AMVIA). Delivered sample now **50**, the preregistered minimum
for EXP-ACQ-0001.
