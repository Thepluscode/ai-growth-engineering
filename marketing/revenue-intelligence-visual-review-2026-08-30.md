# Revenue Intelligence workspace — design pass and visual verification

Date: 2026-08-30
Surface: `http://127.0.0.1:8793/revenue-intelligence`
Store: isolated temporary SQLite databases; the operational store was not changed
Browser: Chromium via Playwright

## Why the first version was rebuilt

The first build was a competent SaaS dashboard, and that was the defect. It opened with a
36 px headline over a radial gradient — a marketing device on an operating screen, which the
brief explicitly ruled out — and then arranged the work into rounded cards. It was
grey-on-white with one indigo accent: the third of the three looks that appear regardless of
subject.

An operating console for one person deciding which revenue action is justified this morning
is not a brochure. This system's own vernacular is evidence: evidence IDs, observation dates,
confidence, gates, provenance, half-lives, `not observed yet`. Its artifact is a **record**.

## The direction

**Machine-recorded fact is set in monospace; human prose in sans.** That inversion of the usual
convention is the point: an ID, a date, a confidence, a gate name and a status are all things
the system observed, and they read as instrument output. A company name, an observed fact and a
commercial hypothesis are prose, and read as prose. The page announces which is which before a
word is read.

**Colour is epistemic, never decorative.** Green marks an observation or a passed gate. Olive
marks an inference or an unknown. Sienna marks something held by a gate. Nothing else on the
page is coloured — no accent, no brand tint, no chart palette.

**The signature is the provenance rule.** An observation earns a ruled ledger line carrying its
date, a measured confidence tick and its source. An inference gets no rule at all — only a left
bar and an olive label:

```
OBSERVED  22 AUG 2026 ──────────────────── ▬▬ 0.80  airwallex.com ↗
The company announced an EMEA expansion on its own newsroom page.

│ INFERRED · NO OBSERVATION
│ Expansion may increase pressure on outbound coverage and reporting.
```

The rule *is* the provenance. An unsupported claim visibly lacks the thing that supports a
supported one. Confidence renders as a measured tick against a hairline track rather than a
progress bar, because it is a reading, not progress toward anything.

Structurally: no hero, no cards. A single dense readout line, then full-bleed hairline-separated
ledgers — queue, held, sources — each row carrying a coloured left edge that states its
epistemic status. Maximum type size on the screen is 19 px, and it is a number.

## Fixture

| Prospect | Gate result | Why |
| --- | --- | --- |
| Airwallex | queued | 3 signals, `observed_published` LinkedIn identity |
| Halted Systems | held | status `disqualified`, despite a 0.9 / 5-of-5 signal and the store's only **verified** identity |
| Unsourced Ltd | held | no target role, no ICP evidence or source, no observed intent event |

Halted Systems is the one that matters. It carries the strongest signal and the only verified
identity in the store, and it never reaches the queue. A score cannot buy past a hard gate.

## Saved sources, scanned live

Two saved careers pages were swept through `POST /api/signals/sources/scan` against the real
internet:

```
Airwallex       https://jobs.ashbyhq.com/airwallex     0 FOUND · 30 AUG 2026
Halted Systems  https://halted.example/careers         FAILED · SOURCE_UNRESOLVED
```

The dead domain failed, was recorded against its own row in sienna, and **did not cost the
other source its result**. That is the behaviour the sweep exists to have, observed live rather
than only in a stub.

## States proved, not asserted

| State | How it was produced | Result |
| --- | --- | --- |
| Populated | seeded isolated store | 1 queued, 2 held, 2 sources |
| Empty | second server on an empty database | "No buyer has passed every gate. The queue stays empty rather than inventing an opportunity." |
| Error | `/api/intelligence` forced to 503 at the fetch boundary | banner `State unavailable`; ledgers read "This is a failure to read state, not an absence of opportunity." |
| Source failure | real DNS failure on a dead domain | per-source `FAILED`, sweep continued |

## Accessibility

- Queue rows are `<button>` elements; the ledger is keyboard reachable.
- Dossier is `role="dialog" aria-modal="true" aria-labelledby="doss-name"`.
- Opening moves focus to the close control; `Escape` closes and returns focus to the originating row.
- `prefers-reduced-motion` disables the dossier and scrim transitions.
- No state is carried by colour alone — every marked row also carries a text label.

## Rendering

| Viewport | Horizontal overflow | Result |
| --- | ---: | --- |
| 1440 × 1000, ledgers | 0 px | PASS |
| 1440 × 1000, dossier open | 0 px | PASS |
| 390 × 844, ledgers | 0 px, 0 elements past the fold | PASS |
| 390 × 844, dossier open | 0 px, nothing clipped | PASS |

Console: 0 errors, 0 warnings from the page. The browser's own `GET /favicon.ico` returns 404;
the server serves no favicon.

## Defects found and fixed during this pass

1. **264 px of mobile overflow.** `.app` used `grid-template-columns:1fr`, whose `auto` minimum let
   the column resolve to its 654 px min-content inside a 390 px viewport. Desktop already used
   `minmax(0,1fr)`; the mobile override had dropped it.
2. **Held rows lost their gate reasons on mobile.** The reasons shared a class with the queue's
   flags, which collapse below 1100 px — hiding the only thing the held section exists to show.
   They now have their own class that survives the collapse.
3. **The 30-second poll rebuilt the queue underneath an open dossier**, replacing the row node and
   breaking focus return. The poll now skips while the dossier is open.
4. **A queue row printed the company name twice** when the signal carried no person name. It now
   names the ICP role still being looked for.
5. **The dossier header repeated its own title and the priority shown two lines below it.**
6. **Signal types rendered as `TECHNOLOGY_CHANGE`.** A signal type is vocabulary and now reads as
   words; an error code stays verbatim, because a code is an identifier you grep for.

## Honest boundary

This verifies rendering, dossier lifecycle, gate presentation, source sweeping and failure states
against seeded isolated stores in Chromium. It does **not** verify: any other browser; production
data; scheduled or unattended scanning (the sweep is still operator-triggered); identity
enrichment beyond the existing public-page provider; or any external execution, which remains
absent by design.
