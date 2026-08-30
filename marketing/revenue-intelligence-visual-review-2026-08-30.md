# Revenue Intelligence workspace — visual verification

Date: 2026-08-30
Surface: `http://127.0.0.1:8791/revenue-intelligence`
Store: isolated temporary SQLite database; the operational store was not changed
Browser: Chromium via Playwright

## Fixture

Three prospects, deliberately chosen so every state is exercised by real gate output rather than by a mock:

| Prospect | Gate result | Why |
| --- | --- | --- |
| Airwallex | eligible | 3 signals, `observed_published` LinkedIn identity |
| Halted Systems | blocked | prospect status is `disqualified`, despite a 0.9 / 5-of-5 signal and a **verified** identity |
| Unsourced Ltd | blocked | no target role, no ICP evidence or source, no observed intent event |

Halted Systems is the one that matters: it carries the strongest signal and the only verified
identity in the store, and it still never reaches the queue. A high score cannot buy past a hard gate.

## What was observed

1. `eligible 1 · blocked 2 · signals 4` — read from `/api/intelligence`, not computed in the page.
2. The queue rendered one row. Halted Systems appeared only under **Blocked prospects**, labelled
   `Prospect status is disqualified`; Unsourced Ltd carried its three distinct reasons.
3. Opening a buyer produced six blocks: Overview, Why now, Signal timeline, Unknowns,
   Commercial lineage, Recommended action.
4. **Why now** rendered the observed vacancy and the commercial reading as two visually distinct
   claims — `OBSERVED` (green, left rule) and `HYPOTHESIS · INFERRED` (amber, left rule) — never as
   one paragraph.
5. The signal timeline listed all three signals newest first (27 Aug, 22 Aug, 10 Aug), each with its
   own evidence id, confidence and source link.
6. Unknowns rendered as first-class rows: deliverability of the observed identity, GTM stack, budget,
   current vendor, buying authority.
7. Commercial lineage showed 3 observed stages (signal, evidence, identity) and 6 rendered as
   `Not observed yet`. Nothing downstream was invented.
8. Authority remained `R3 · APPROVAL REQUIRED`; the drawer offers no send control.

## States proved, not asserted

| State | How it was produced | Result |
| --- | --- | --- |
| Populated | seeded isolated store | 1 queued, 2 blocked |
| Empty | second server on an empty database | "No eligible buyers. The queue stays empty rather than inventing opportunity." |
| Error | `/api/intelligence` forced to 503 at the fetch boundary | red banner `/api/intelligence failed: 503`; queue and blocked list both read "Data unavailable — this is an error, not an empty result." |

The error case is the one worth stating plainly: a failed API does **not** render as zero opportunity.

## Accessibility

- Buyer rows are `<button>` elements, so the queue is keyboard reachable.
- Drawer is `role="dialog" aria-modal="true" aria-labelledby="drawer-title"`.
- Opening moves focus to the close control; `Escape` closes and returns focus to the originating row.
- `prefers-reduced-motion` disables the drawer and scrim transitions.
- No state is communicated by colour alone — every badge carries a text label.

## Rendering

| Viewport | Horizontal overflow | Result |
| --- | ---: | --- |
| 1440 × 1000, queue | 0 px | PASS |
| 1440 × 1000, drawer open | 0 px | PASS |
| 390 × 844, queue | 0 px | PASS |
| 390 × 844, drawer open | 0 px, nothing clipped | PASS |

A real defect was found and fixed during this pass: the mobile rule set `.app` to
`grid-template-columns:1fr`, whose `auto` minimum let the grid column resolve to its 654 px
min-content inside a 390 px viewport — **264 px of horizontal overflow**. The desktop rule already
used `minmax(0,1fr)`; the mobile override had dropped it. Two further defects were corrected in the
same pass: the 30-second poll rebuilt the queue underneath an open drawer (breaking focus return),
and a buyer row printed the company name twice when the signal carried no person name.

Console: 0 errors, 0 warnings from the page. The browser's own `GET /favicon.ico` returns 404;
the server serves no favicon.

## Honest boundary

This verifies the workspace's rendering, drawer lifecycle, gate presentation and failure states
against a seeded isolated store in Chromium. It does **not** verify: any other browser; production
data; scheduled signal acquisition; identity enrichment beyond the existing public-page provider;
or any external execution, which remains absent by design. Screenshot capture was attempted and the
tool reported success, but no file was written to disk — the rendering claims above therefore rest on
measured DOM geometry, not on images.
