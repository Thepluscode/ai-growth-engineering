# Growth Leak Teardown — CloudTech24

Research date: 2026-08-19

## ICP fit

- **Observed:** UK-headquartered managed IT and cybersecurity provider serving SMEs and international clients; the site reports 250+ customers across 10+ countries.
- **Inferred:** Strong fit for the UK cyber/MSP wedge. Head of Sales John Hosegood is the most relevant named commercial recipient.

## Current offer

- **Observed:** 24/7 managed IT and cybersecurity spanning assessments, penetration testing, MDR, threat hunting, compliance, incident response, Microsoft 365 security assessment, and IT support.
- **Observed:** Security assessments already exist as a defined service.

## Primary CTA

- **Observed:** “Book a discovery call” appears on the homepage, cyber-services pages, assessment pages, and contact page.

## Acquisition surfaces

- **Observed:** Homepage; service and sub-service pages; UK/location pages; customer reviews; case/testimonial content; resource/blog pages; contact page.

## Observable funnel

- **Observed:** Service or location page → repeated discovery-call CTA → booking/contact route.
- **Unknown:** Traffic, CTA click rate, form completion, qualified booking rate, pipeline, CAC, and close rate.

## Proof

- **Observed:** The cyber-services page reports 96% year-over-year retention, 250+ customers, and average issue resolution under 68 minutes; the site also displays Google and Trustpilot ratings and named leadership.
- **Observed:** A Microsoft 365 security-audit testimonial describes a concrete audit deliverable.

## Likely commercial leak

- **Inference, not diagnosis:** High-intent assessment buyers may be asked to take the same generic “discovery call” step as broad managed-service buyers, despite CloudTech24 already having specific assessment products and proof. That may suppress qualified conversations from visitors who want a bounded first step.

## Competitor patterns

1. **Netitude:** leads with a defined IT audit, describes the report and four-step process, and makes the audit the normal first step ([source](https://www.netitude.co.uk/it-audit)).
2. **The HBP Group:** names a “360° Assessment” and describes its executive-level output—a roadmap exposing risks and bottlenecks ([source](https://thehbpgroup.co.uk/)).
3. **Secure Chain:** offers a complimentary posture assessment with a short problem-context form ([source](https://securechaingroup.com/)).

## Sharpest observed leak — the entry offer exists and is unlinked

- **Observed:** `/landing-page/free-90-day-email-scan/` is live and explicitly free: “Discover hidden
  threats with a free email security healthcheck” … “It’s free, with no obligation to continue after
  the first scan.” It scans 90 days of inbox activity and returns a report of harmful emails found.
- **Observed:** it is absent from the homepage’s complete internal link list (97 internal links
  enumerated) and absent from the main navigation (9 top-level items, no offer or resources entry).
- **Observed:** it is absent from the complete internal link list of
  `/service/cyber-security-services/managed-email-security/` — the most topically adjacent page on
  the site.
- **Unknown, and the first question to ask them:** whether that page already has its own paid/ads
  traffic source. If it does, this is a single-channel offer rather than an orphaned one, and the
  diagnosis changes. Do not assert the leak before they answer.
- **Unverified, not absent:** form fields on `/contact/` and on the scan page. Extraction returned no
  form markup on either, but embedded/JS-rendered forms are routinely stripped in conversion.

This strengthens rather than replaces the assessment-CTA hypothesis below: CloudTech24 has already
built the bounded first step, so the cheapest test is routing to it, not creating one.

## Second-order finding — vendors publish their proof and they do not

PowerDMARC, IRONSCALES and ID Agent each host a CloudTech24 case study. No named client or case study
appears on the homepage, `/cyber-security-services/`, `/managed-it-services/` or
`/location/it-support-london/`. The write-ups exist and were already approved. Raise it once a
conversation is open; do not lead with it.

## One hypothesis

An assessment-specific CTA with an explicit deliverable will produce a higher qualified-booking rate from assessment and compliance pages than “Book a discovery call.”

## One proposed experiment

Route to the offer they already own. Add the free 90-day email scan as a **secondary** CTA in two
places only — the homepage hero, beside the existing “Book a discovery call”, and the top of
`/service/cyber-security-services/managed-email-security/`. The primary CTA does not change.

- **Baseline:** current weekly scan requests and discovery-call bookings — CloudTech24 must supply
  these before launch. Without a baseline the result is uninterpretable and INVALID by their own rule.
- **Primary metric:** `qualified_scan_requests_per_1000_sessions` on the two changed pages
- **Minimum sample:** 4 weeks or 1,000 sessions across both pages, whichever comes later
- **Guardrail:** weekly discovery-call bookings must not fall more than 10% — this is what stops a
  cheap conversion win cannibalising the expensive one
- **KEEP:** ≥3 additional scan requests per 1,000 sessions with the guardrail intact
- **REVIEW:** <1 additional per 1,000 sessions, or guardrail breached
- **Between the two:** ITERATE on placement and label before concluding the offer itself is wrong

If they confirm the scan page already has its own traffic source, fall back to the assessment-CTA
test: on the Microsoft 365 security-assessment and core cyber-assessment pages only, replace the
generic CTA for one cohort with “Request a Microsoft 365 Security Snapshot”, promising only a scoped
review and sample output.

## Sources

- [CloudTech24 homepage](https://cloudtech24.com/)
- [Cybersecurity services](https://cloudtech24.com/cyber-security-services/)
- [Cybersecurity assessments](https://cloudtech24.com/service/cyber-security-services/cyber-security-assessments/)
- [Contact](https://cloudtech24.com/contact/)
- [Team](https://cloudtech24.com/meet-the-team/)
- [Microsoft 365 audit testimonial](https://cloudtech24.com/2022/11/cloudtech24s-new-website/)
- [Free 90-day email scan](https://cloudtech24.com/landing-page/free-90-day-email-scan/)
- [Managed email security](https://cloudtech24.com/service/cyber-security-services/managed-email-security/)
- [Managed IT services](https://cloudtech24.com/managed-it-services/)
- [IT support London](https://cloudtech24.com/location/it-support-london/)
- [PowerDMARC MSP case study](https://powerdmarc.com/msp-case-study-cloudtech24/)
- [IRONSCALES case study](https://ironscales.com/case-studies/cloudtech24)
- [ID Agent case study](https://www.idagent.com/case-studies/cloudtech24/)
