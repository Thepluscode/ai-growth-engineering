# EXP-ACQ-0001 — verdict at minimum sample

**Recorded:** 2026-08-27 · **Decision:** `REVIEW` · **Sample:** 50 / 50 minimum

Preregistered on 2026-08-19: KEEP at >=10% meaningful reply rate, ITERATE at 5-9.9%,
REVIEW below 5%, no verdict before 50 confirmed sends. The minimum is now met, so the
verdict is due whether or not it is welcome.

```
$ age import-outreach --db .age/growth.db experiments/EXP-ACQ-0001/sales/outreach.csv
imported 55 sends, skipped 0

$ age scoreboard --db .age/growth.db
outreach_sent                          50 / 100
meaningful_responses                    0 / 20

$ age experiment-result --db .age/growth.db --experiment-id EXP-ACQ-0001 \
    --sample-size 50 --observed-value 0.0
review
```

55 rows, 50 counted: five bounces are not sends. `REVIEW` means "below the line, come and
look". It is not a judgement on the business, and it does not authorise a product change.

## What 0/50 does and does not rule out

| | |
|---|---|
| Observed | 0 / 50 = 0%, Wilson 95% CI **0 - 7.1%** |
| P(0 replies given a true 10% rate) | **0.52%** |
| P(0 replies given a true 5% rate) | **7.7%** |

The KEEP threshold is dead: a 10% rate would have produced at least one reply 99.5% of the
time. The REVIEW threshold is only mostly dead — a true 5% channel returns this result once
in thirteen runs, which is uncomfortable rather than impossible.

## The finding that matters more than the rate

**48 of the 50 sends went to a role inbox.** Two reached a named person's own address.

```
info@ / contact@ / enquiries@ / sales@ / support@ / cyber@ / cra@ / uksales@ / tellmemore@   48
a named buyer's own mailbox (Blue Frontier, Technical Drive)                                  2
```

So the channel that was actually tested is **cold email to a shared inbox at a UK MSP**, not
cold email to a buyer. Those are different channels with different priors, and the
preregistration named neither — it said "qualified sends", and a send to `info@` satisfied
that wording while failing its intent.

What each sub-channel can support:

| Sub-channel | n | P(0 replies at a true 10%) | Conclusion available |
|---|---|---|---|
| Role inbox | 48 | 0.6% | 10% is ruled out for this route |
| Named buyer | 2 | 81% | **Nothing.** Untested |

The named-buyer route was not tested and cannot be reported as having failed. This is the
same false negative that `strategy/sl2-send-tracker.csv` produced in a smaller form: a
delivery defect read as a market response.

## What this authorises

1. **Recording the verdict.** Done, above.
2. **Nothing else automatically.** The freeze in `FEATURE_TRACKER.md` holds; no product
   feature is authorised by this result.

## What a person has to decide

The choice is not "is outbound dead" — that question was never asked cleanly. It is:

- **Re-run the wedge against named buyers** with a fresh preregistration, contact
  discovery as an explicit gate, and a routing requirement that a send to `info@` does not
  satisfy; or
- **Accept the role-inbox result as the answer for this ICP** and move the constraint to
  another channel, in which case the owned site becomes the live surface and
  `marketing/owned-site-baseline.md` is the work; or
- **Question the offer rather than the route.** 0/48 to shared inboxes is consistent with
  both "the message never reached anyone" and "it reached a gatekeeper who did not care".
  These are separable only by testing the named-buyer route.

The system does not choose between these.

## Contract change this earns

"Qualified send" must be defined by **who receives it**, not by whether it left the outbox.
Any successor experiment records a `recipient_class` of `named_buyer` or `role_inbox` per
send and reports the two rates separately. A blended rate across the two hides exactly the
thing this experiment found.
