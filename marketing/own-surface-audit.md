# Own-Surface Audit — ThePlus-Tech

**Date:** 2026-08-19 (corrected and actioned 2026-08-20) · **Scope:** the digital surface we own, audited the same way we audit a prospect.
**Method:** live fetch, DNS, HTTP headers, full page source (118KB). Public sources only.

The Digital Marketing Project has run one channel — outbound — for a structural reason, not a
strategic one: **outbound is the only channel that works without measurement.** Sends can be counted
in a spreadsheet. SEO, content, paid, CRO, email and partner work all require analytics and a capture
mechanism, and we have neither. That is the finding, and it gates every non-ACQ experiment.

---

## 1. Domains

| Domain | Result | Note |
|---|---|---|
| `theplus-tech.com` | **200** | Live, served by Vercel, HSTS set |
| `www.theplus-tech.com` | **000 — connection failure** | Not reachable. Anyone typing `www.` gets nothing |
| `theplus.tech` | **404** | On Wix nameservers, serving nothing |
| `www.theplus.tech` | **404** | Same |

`knowledge-base/company-overview.md` records **"Web. www.theplus.tech"**. That domain does not serve
a site. The live site is on a different domain the KB does not name. Verified by curl on three URL
forms plus `dig` — not a single-tool artifact.

## 2. Measurement — absent

Checked the full 118KB body for nine vendors: `gtag`, Google Tag Manager, google-analytics, Plausible,
PostHog, Fathom, Umami, Clarity, Hotjar. **None present.**

Consequences, stated plainly:
- No baseline exists for any page, so no CRO experiment can declare a control.
- No traffic figure exists, so no SEO or content experiment has a denominator.
- No source attribution exists, so the `attribution` registry can never be populated from this site.
- Spend on any paid channel would be unattributable to revenue, which makes `allowable_cac`
  uncomputable and `scale_verdict` return `INSUFFICIENT_DATA` by construction.

## 3. Capture — absent

- **A real `<form>` exists** in `App.tsx` with validation and a selected engagement model. It is absent
  from the *served* HTML because the site is a client-rendered SPA — my first pass grepped the shell
  and called the form missing. Corrected 2026-08-20.
- **It terminates in a `mailto:` draft, not a submission.** There is no backend, no thank-you URL, and
  before 2026-08-20 no event fired, so a completed form was indistinguishable from a bounce.
- **16 `mailto:` links.** A mailto cannot be measured, cannot be A/B tested, has no thank-you state
  to fire a conversion on, and is filtered or broken for anyone without a configured desktop client.
- No canonical link tag. OG and Twitter card tags are present.

## 4. Offer — four different ones across four artifacts

| Where | Offer |
|---|---|
| This repo's README | Growth Leak Teardown → 30-Day Pipeline Engineering Sprint |
| `sites/theplus-tech.com/index.html` (unpublished) | £1,200 one-day AI compliance diagnostic |
| Live site | Architecture assessment · technical briefing · design-partner pilot — no price |
| `company-overview.md` | "Governed coordination fabric for software agents and physical machines" |

Six distinct CTAs on the live page: *Explore the Control Plane*, *Book an architecture assessment*,
*Book a technical briefing*, *Request subscription*, *Start assessment*, *Apply for a design-partner
pilot*. Our own Rule of One says one offer and one CTA during validation. The site runs six.

This is the same defect we billed CloudTech24 for, one level worse: they had one CTA everywhere and
an orphaned offer; we have four offers and no measurement.

## 5. What is fact, inference and unknown

**Observed:** every domain result, the absence of analytics tags and `<form>` in the source, 16
mailto links, the six CTA labels, the four offers, robots.txt and sitemap.xml both returning 200.

**Inferred:** that the missing measurement is *why* only outbound has run. Well-supported by the
capability map — every zero-row registry depends on data this surface cannot produce — but not proven.

**Unknown:**
- Current traffic to `theplus-tech.com`. Nothing on the page reports it and no analytics exists to ask.
- Whether Vercel Analytics is enabled at the platform level rather than via a script tag. This would
  not appear in page source. **Check the Vercel dashboard before concluding measurement is absent** —
  it is the one explanation for these observations that does not involve a missing tag.
- Whether the assessment questionnaire posts anywhere, and where submissions land.
- Search visibility. A sitemap exists; whether anything ranks is unmeasured.

## 6. What has to be true before any channel experiment can run

Not experiments — prerequisites. An experiment declared before these exist would be unfalsifiable.

| # | Prerequisite | Status |
|---|---|---|
| 1 | Fix `www.theplus-tech.com` — half of typed traffic was failing | **DONE 2026-08-20** — CNAME at Cloudflare, 307 to apex, valid cert |
| 2 | Install one analytics tool | **DONE 2026-08-20** — Vercel Web Analytics live; `contact_intent` verified end to end in the dashboard |
| 3 | A capture step that fires a measurable conversion event | **PARTIAL** — the mailto click is measured and labelled by offer; there is still no backend form and no captured contact |
| 4 | Reconcile four offers, or register each with its own buyer | **DONE** — all four in the `offers` registry, conflict now visible as data |
| 5 | Correct `company-overview.md` web address | **DONE** — corrected to `theplus-tech.com` with the error noted |

### 1 is the one blocking item, and only you can do it

Vercel dashboard → project `theplus-tech-website` → Settings → Domains → add
`www.theplus-tech.com` and set it to redirect to the apex. There is no `vercel` CLI and no
`VERCEL_TOKEN` on this machine, so this cannot be scripted from here.

Verify afterwards with content, not a status code:

```bash
curl -s -o /dev/null -w '%{http_code} -> %{url_effective}\n' -L https://www.theplus-tech.com
# expect 200 -> https://theplus-tech.com/
```

### To land the instrumentation

```bash
cd <a clone of theplus-tech-website>
git fetch <this branch> && git push origin instrument-conversion-funnel
```

Pushing to `main` auto-deploys to production, which is publishing — gated under
`AP-MC-WARM-003-1`, so I stopped at a local commit.

Only then do `EXP-CRO-0001` (mailto vs form), `EXP-SEO-0001` (problem-led search) and
`EXP-CONTENT-0001` become runnable rather than decorative.

## 7. What this audit does not authorise

Publishing or editing the live site is gated under Rule 0.6 pending `AP-MC-WARM-003-1`. Nothing here
changes any live surface. This is diagnosis only.
