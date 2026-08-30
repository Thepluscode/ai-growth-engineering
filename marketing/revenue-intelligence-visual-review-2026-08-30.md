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

## Commercial performance

The funnel surface was verified against a fixture carrying all three states at once — 12
delivered sends, 2 meaningful replies, 1 discovery call and nothing below it:

```
Meaningful reply rate            2 of 12 outreach sent          16.7%   ▬▬▬────────────
Discovery rate                   1 of 2 meaningful responses    50.0%   ▬▬▬▬▬▬▬▬───────
Diagnostic rate                  0 of 1 discovery calls          0.0%   ───────────────
Proposal rate                    0 of 0 diagnostics proposed  NOT ASKED ┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈
Win rate                         0 of 0 commercial proposals  NOT ASKED ┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈
Delivered outreach to customer   0 of 12 outreach sent           0.0%   ───────────────
```

A measured zero sits on a solid track in ink; a question nobody asked sits on a dashed track
in olive. They are the same shape and never the same reading. On an empty store all six steps
render `NOT ASKED` rather than six zero percentages.

`CAC, LTV and payback` render as **not derivable**, with the reason: the engine computes them,
but nothing records acquisition spend, monthly revenue or churn. An absence with a cause is
information; a zero would be a claim.

Mutation check: making a zero denominator report `0.0` turns four funnel tests red. Restored
clean.

## Density pass

The screen was crowded with prose. Every section carried a two-to-three-line paragraph
explaining doctrine before the reader reached any data — including one that explained the
funnel's zero-denominator rule on screen, which is a design decision belonging in this document
rather than in the interface. An operator who opens this daily does not need to be told what a
gate is each morning.

All of it was cut: seven section paragraphs, four readout captions, and the title/body pairs in
every empty state. Measured at 1440 px against the same fixture:

| | Before | After |
| --- | ---: | ---: |
| Prose characters on the sheet | 1210 | 114 |
| Prose blocks | 15 | 4 |
| Page height | 1721 px | 1405 px |
| Data rows | 21 | 21 |

The four remaining fragments are all data, not explanation: two unknowns stating their cause
("Unknown — nobody has paid", "Not derivable — no spend, revenue or churn recorded") and two
empty states. Nothing informational was lost — the data-row count is unchanged, and the held
rows still carry every gate reason as a chip, at both viewports.

## Scheduled sweep

`age sweep-sources` runs the sweep unattended; `scripts/sweep-cron.sh install` puts it in cron
at 07:00 daily. A sweep records nothing as a signal — candidates persist as **pending
proposals**, and the workspace gained an `Awaiting review` counter and ledger showing each one
with its strength, confidence, candidate id, source link and a `not a signal yet` mark.

Two guards make unattended running safe. Both were mutation-verified against a green baseline:

| Guard | Mutation | Result |
| --- | --- | --- |
| `--min-interval-hours 20` skips a recently fetched source | replaced the interval test with `if False` | one test red, precisely |
| a conflict refreshes only `last_seen_at` | added `status = excluded.status` | one test red, precisely |

The second is the one that matters over time: without it, every sweep would resurrect a
candidate the operator had already dismissed.

### Verified live, not only in stubs

- The exact cron command runs under `env -i HOME=... PATH=/usr/bin:/bin` and exits 0.
- Three real UK MSP careers pages swept clean; the immediate re-run correctly reported
  `scanned 0/3 (skipped 3)` with `scanned 0.0h ago, inside the 20h interval` against each.
- Install → remove → install → install left 6 active cron entries and 9 other-project entries
  untouched, with the marker count going 5 → 0 → 5.

### The zero was checked before it was believed

All three sources returned 0 candidates. That is a result a broken connector also produces, so
it was checked rather than reported: Texaport publishes four real vacancies
(`it-support-analyst-apac`, `2nd-line-support-engineer-sao-paulo`, `cloud-engineer-uk`,
`1st-line-support-engineer-mexico`), none of which is a commercial role. A positive control on
the same live HTML — one title relabelled to `Head of Revenue Operations` — yields exactly one
candidate. The pipeline reaches the links; the role filter is what rejects them.

**This does not yet fill the queue.** Three sources that are hiring support engineers produce
nothing to rank, and that is the honest state: the schedule is the mechanism, sources are the
input, and three is not enough. Widening the source list is the next move, not another
mechanism.

## Careers-page discovery across the prospect list

`age discover-sources` reads each prospect's home page, finds careers links by path **and** by
link text (plenty of sites route careers through a CMS slug no path pattern would catch, while
the link still says "Join us"), scans the best one, and keeps a source only where a commercial
vacancy is published.

Run across all 51 non-disqualified prospects on 2026-08-30 — the 12 disqualified were skipped
because a disqualified prospect cannot enter the queue anyway, and sweeping them would spend
somebody else's bandwidth for nothing:

| Outcome | Count |
| --- | ---: |
| Published a commercial role → **kept** | 3 |
| Careers page read, no commercial vacancy | 29 |
| No careers link on the home page | 16 |
| Site unreachable | 3 |

Kept: Atlas Cloud (`Customer Success Manager (CSM)`), Blue Frontier (`Digital Marketing`),
The HBP Group (`Sales Careers at The HBP Group`). All three are seeded in
`seeds/registries.json` and swept into three candidates awaiting review.

Those four outcomes stay distinct on purpose. An unreachable host reported as "not hiring" is a
market answer that was never given — the same false-negative shape that nearly killed a live
offer at n=6. Mutating `site_unreachable` to report `no_commercial_role` turns that test red.

### A defect the first run surfaced

The first pass reported Atlas Cloud's vacancy title as roughly three thousand characters of body
copy. Its careers page wraps an entire job card in one anchor, and the careers-link branch took
the whole anchor text as the title — which would have written a paragraph into the observed fact
and from there into the evidence chain.

The fix has two bounds: cut at the first job-card field label (`Department:`, `Full Time`, `£`,
`About`, and similar conventional labels, not one site's markup), then at a hard 90-character cap.
Titles went from ~3000 characters to 30. It also removed two false positives that only passed
because the blob contained commercial words in its body copy — a `Virtual Chief Information
Officer` and an `IT Solutions Presales Engineer` are not commercial roles, and both are now
correctly rejected. The first run's data was discarded and discovery re-run clean.

**Both bounds initially survived mutation.** The first version of these tests asserted nothing
that pinned them: one duplicated a check `_candidate_from_record` already made, and the other
used a fixture containing a field label, so the character cap never engaged. The redundant check
was removed — one enforcement point beats two, because a duplicated guard is a guard nobody can
mutation-test — and a label-free fixture was added. Both mutations now kill precisely.

### Held versus never observed

Against the real store the held ledger rendered all 63 prospects, 51 of them saying only
"No observed intent event". That is not a gate rejecting a prospect; it is a prospect nobody has
looked at, and rendering the two identically buried the twelve that were genuinely disqualified.
The ledger now lists the gated rows with their real reasons and summarises the rest:
`51 prospects carry no observed signal yet. Not held by a gate — not yet looked at.`

### What this does not achieve

**The queue is still zero.** Three candidates awaiting review are not three ranked buyers: a
candidate is not a signal, and a signal without a resolved identity is not a reachable buyer.
Sixteen prospects exposing no careers link is also a real ceiling — a third of the list — most
likely JavaScript-rendered navigation or careers hosted on a subdomain, neither of which this
connector reads.

## The first ranked buyer, and the two that were rejected

Three swept candidates were reviewed against their live sources. Two did not survive, and each
exposed a defect the review existed to catch.

**Blue Frontier — rejected.** The candidate's URL was `https://www.bluefrontier.co.uk/careers#`:
the careers page itself. The text "Digital Marketing" is Blue Frontier's own *service line* in
site navigation, not a vacancy. A link back to the index is the page, not a role on it — the
connector now rejects same-page links.

**The HBP Group — rejected.** `/jobs/sales-careers` is an evergreen talent pool — *"Are you a
sales professional looking to advance your career?"* — one of a family with `/jobs/it-careers`,
`/jobs/erp-careers`, `/jobs/epos-careers` and `/jobs/future-opportunities`. Every vacancy HBP
actually publishes is technical: presales engineers, infrastructure consultants, Sage
consultants. Recording it would have stated the company was hiring for something it never
advertised. The connector now rejects talent-pool slugs.

Both dismissals carry their reason. `set_candidate_status` refuses a dismissal without one,
because a dismissal with no reason is a deletion — the same silent discard the held ledger
exists to prevent.

**Atlas Cloud — recorded as `SIG-349ABEAEF68B`.** Verified against the live page: a distinct
vacancy at its own URL, `https://atlascloud.co.uk/jobs/customer-success-manager-csm/`, listed
under *Department: Sales*, whose stated success metrics are gross and net revenue retention and
cross-sell revenue. The commercial reading is recorded as inference and states plainly that a
vacancy does not establish budget, vendor demand or buying intent.

### The identity, and the two that were refused

The bounded public-page provider returned 11 candidates from Atlas Cloud's own about page: nine
named LinkedIn profiles and two role inboxes, `hello@` and `servicedesk@`. **The role inboxes
were deliberately not recorded.** Eight of seventeen sends in the SL2 tracker went to role
inboxes and were read as market rejection when they were delivery defects; recording one here
would rebuild that failure.

The prospect's declared ICP roles are *CEO; Head of Cyber Security; Account Director*. Two are
published — Pete Watson (Chief Executive Officer) and Joe McLeod (Account Director). The CEO was
recorded, because the signal is a change of operating model rather than an account-level
question. It is labelled `observed_published`, not verified, and the dossier lists
`Deliverability of this identity — UNVERIFIED` as a first-class unknown.

No person was named in the vacancy itself, so no person was retrofitted onto the signal. The
queue row reads `Looking for CEO; Head of Cyber Security; Account Director`.

### Where it stands

```
Queued 1 · Held 62 · Signals 1 · Sources 3 · Awaiting review 0

Atlas Cloud   priority 53.2   fit 0.75 · strength 0.8 · confidence 0.9 · freshness 0.986
              route linkedin · identity observed_published
              action prepare_approval_draft · authority R3
```

**No contact has been made, and none can be made from this screen.**

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
