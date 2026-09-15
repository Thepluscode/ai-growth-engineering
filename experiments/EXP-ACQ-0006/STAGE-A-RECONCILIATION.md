# EXP-ACQ-0006 — Stage A send reconciliation (2026-09-15)

The historical record says 22 Stage A sends on 2026-09-08 (1 hard bounce, 21 awaiting). The first
Gmail link found 19. This reconciles the difference before any send enters the canonical funnel.
Only a send backed by a real Gmail message becomes a `message_sent` event; the historical claim is
preserved here and in the imported queue, not converted into events.

## Method

- **Sent mail:** Gmail read-only search `in:sent after:2026/09/07 before:2026/09/10`, first without
  and then **with Trash**. The first link used the default search, which omits trashed messages.
- **Mapping:** each recipient address was matched exactly to one prospect record in the frozen
  queue. No match relied on a domain alone.
- **OEC:** searched `in:anywhere` with Trash for any message to, from or mentioning the domain or
  the company.
- **Positive control:** the identical query form for Waterworx returns its trashed send, so an
  empty result means no record, not a failed search.
- **Safe House:** the delivery-failure message was read in full.

## Result

| Classification | Count |
|---|---|
| VERIFIED_GMAIL_SEND | 21 |
| VERIFIED_NON_GMAIL_SEND | 0 |
| DUPLICATE_RECORD | 0 |
| NOT_ACTUALLY_SENT | 0 |
| UNKNOWN | 1 |

`UNVERIFIED_STAGE_A_SENDS = 1`

| Ref | Company | Classification | Note |
|---|---|---|---|
| FSP-0001 | Stonehenge Plumbing and Heating Ltd | VERIFIED_GMAIL_SEND | |
| FSP-0002 | Waterworx Plumbing & Heating Services | VERIFIED_GMAIL_SEND | in Trash; 08:27:20Z. The queue recorded no send time because its search skipped Trash |
| FSP-0003 | John Williams Heating Services | VERIFIED_GMAIL_SEND | |
| FSP-0004 | Oldroyd Group (OMS Oldroyd) | VERIFIED_GMAIL_SEND | |
| FSP-0007 | Essex Heating Engineers | VERIFIED_GMAIL_SEND | |
| FSP-0008 | Serviceteam | VERIFIED_GMAIL_SEND | |
| FSP-0009 | Safe House Services | VERIFIED_GMAIL_SEND | in Trash; 07:29:22Z. Hard bounce 11 s later (550 5.1.1, account does not exist). The queue's 08:29:00Z was local time written as UTC |
| FSP-0011 | Rowlen Boiler Services | VERIFIED_GMAIL_SEND | |
| FSP-0013 | Stator Electrical Solutions | VERIFIED_GMAIL_SEND | |
| FSP-0017 | GT Bathrooms & Boilers Ltd | VERIFIED_GMAIL_SEND | |
| FSP-0019 | Summit Plumbing & Heating Ltd | VERIFIED_GMAIL_SEND | |
| FSP-0023 | Will Stone Gas Plumbing and Heating Ltd | VERIFIED_GMAIL_SEND | |
| FSP-0025 | Manchester EICR / Manchester Gas | VERIFIED_GMAIL_SEND | in Trash; 07:31:38Z |
| FSP-0026 | OEC (Electrical) Ltd | UNKNOWN | no Gmail message to, from or about the company anywhere, Trash included. The queue's "sent" rests on an empty drafts folder. A missing record does not prove it was never sent, so it is not NOT_ACTUALLY_SENT |
| FSP-0031 | PSS Installations | VERIFIED_GMAIL_SEND | |
| FSP-0032 | Martin Day Commercial Electricians | VERIFIED_GMAIL_SEND | |
| FSP-0033 | Celsius Plumbing & Heating | VERIFIED_GMAIL_SEND | |
| FSP-0036 | Smart Plumbing & Heating Bristol | VERIFIED_GMAIL_SEND | |
| FSP-0038 | 247 Emergency Plumbing Scotland | VERIFIED_GMAIL_SEND | |
| FSP-0040 | Paul Harvey Plumbing & Heating | VERIFIED_GMAIL_SEND | |
| FSP-0042 | Hertz Electrical Contractors | VERIFIED_GMAIL_SEND | |
| FSP-0043 | First Call Electrical Contractors | VERIFIED_GMAIL_SEND | |

## What this means for the funnel

- **Attempted sends:** 21 canonical `message_sent` events, each keyed on its Gmail message id.
- **Bounced:** 1 (Safe House), recorded as `message_bounced` through the reply-review approval.
- **Delivered exposures:** 20. Every response rate for this experiment uses 20, never 21 or 22.
- **OEC:** stays out of the funnel unless a real source for its send is found.
- **Non-response:** the verdict still waits for 2026-09-22. A real reply before then counts
  immediately.
