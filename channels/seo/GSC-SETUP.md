# Google Search Console — what is already true, and the one action left

Organic search is `unmeasurable`, not `not_started`. `robots.txt` and `sitemap.xml` both serve 200
and the sitemap is well-formed, so nothing is broken; there is simply **no denominator**, because
Search Console is not connected. Without it, "are we indexed" and "for what" are unanswerable —
the searches run from here found nothing from the domain, but the tool available is US-only, is not
necessarily Google's index, and silently ignored a `site:` operator rather than honouring it. That
is not proof of non-indexation, and it should not be recorded as one.

## Verification is probably already done

The domain already carries a Google verification token:

```
$ dig +short TXT theplus-tech.com
"google-site-verification=vvkI4omOpS7EuCwrFFX9TZ_zaoGMyA-P2WGToq9d8tQ"
"v=spf1 include:_spf.google.com ~all"
```

Google uses **one** verification system for Search Console and Workspace, and the SPF record beside
it points at Google Workspace — so this token was most likely created when the mail domain was set
up. Tokens are per-Google-account, so:

- **If Search Console is opened with the same Google account**, adding a Domain property for
  `theplus-tech.com` should verify **immediately**, using the record already present. No DNS change,
  no site change, no deploy.
- **If it is a different account**, Google issues a new token and it goes in Cloudflare as a second
  TXT record on the apex. Multiple `google-site-verification` records coexist; do not replace the
  existing one — that would break whatever depends on it.

DNS is on **Cloudflare** (`ian.ns.cloudflare.com`, `brianna.ns.cloudflare.com`), not Vercel, so any
new record is added in the Cloudflare dashboard. Vercel's `dns ls` shows its own view of a domain it
does not authoritatively serve, which is why it lists ALIAS and CAA records but none of the TXT.

## The action

1. Open Search Console, add a **Domain** property (not a URL-prefix property) for
   `theplus-tech.com`. Domain properties cover `www`, subdomains and both schemes in one.
2. If it verifies straight away, submit `https://theplus-tech.com/sitemap.xml`.
3. If it asks for a new TXT, add it in Cloudflare **alongside** the existing one and re-verify.

Two minutes if the account matches. It is an account action, not a code change, which is why it sits
with a person rather than being done here.

## What it unlocks

Impressions, clicks, average position and the queries the site actually appears for — the
denominator organic search has never had. Until then the channel cannot be judged, and judging it
without those figures would be the same mistake as the withdrawn `EV-BASELINE-01`.

## Deliberately not done

- **The sitemap's stale `lastmod`** (`2026-08-13` on every URL). Production serves a static
  `public/sitemap.xml` from `main`; the `redesign/v2` branch already replaces it with a generated
  `app/sitemap.ts`. Patching `main` would duplicate work a merge delivers.
- **Any other SEO work.** The site has ~47 visitors a month and no Search Console. Tuning a page
  nobody can measure is the activity that looks like progress.
