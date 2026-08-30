# Public hiring signal connector — visual verification

Date: 2026-08-30  
Surface: `http://127.0.0.1:8790/#intelligence`  
Store: isolated temporary SQLite database; the operational store was not changed

## Live source

- Company: Airwallex
- Source: `https://jobs.ashbyhq.com/airwallex/d0ee1c45-2b64-4abe-ad5c-75e0efd8d91e`
- Observed posting: `Manager, Revenue Strategy & Operations, UK & Europe`
- Posting date returned by structured evidence: `2026-08-10`
- Connector result: one preview candidate, `structured_job_posting`, source confidence `0.95`

## Lifecycle observed

1. The scan returned one candidate without persisting it.
2. The candidate displayed the observed vacancy separately from the commercial hypothesis.
3. The interface stated that hiring does not establish budget, vendor demand or buying intent.
4. `Record reviewed signal` persisted one signal and sent nothing.
5. The buyer desk changed from `0 eligible · 1 held by gate` to `1 eligible · 0 held by gate`.
6. The next action was `Research recipient identity`; no identity was invented.
7. A second scan rendered `Recorded · SIG-…` disabled, rather than offering a duplicate import.
8. The isolated store contained one intent signal, zero outbound drafts and zero outreach rows.

## Rendering

| Viewport | Horizontal overflow | Result |
| --- | ---: | --- |
| 1440 × 1000 | 0 px | PASS |
| 390 × 844 | 0 px | PASS |

At mobile width the scan form measured 314 px and the evidence candidate measured 286 px. Observed and inferred blocks remained readable. Browser console: 0 errors, 0 warnings.

## Honest boundary

This verifies one on-demand public hiring connector and its review/import flow. It does not verify scheduled morning scans, bulk source coverage, named-buyer identity resolution or external execution.
