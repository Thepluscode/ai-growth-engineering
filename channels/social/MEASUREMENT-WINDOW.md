# LinkedIn organic — measurement period, not an experiment

**Opens:** on the first post · **Minimum:** 8 posts · **Surface:** founder profile, not a company page

Deliberately **not** an experiment. Nothing is preregistered, there is no hypothesis, no variant and
no verdict, so it gets no `EXP-` id. `EXP-CREATIVE-0001` was blocked for exactly the error this
avoids: setting thresholds with no baseline. This window exists to produce the baseline.

## The question it answers

Not "does the content perform". **"Do UK MSP commercial decision-makers actually see it."**

That is the whole reason this channel was chosen over the others in `CHANNEL-SCREEN.md`. Discovery
found named decision-makers with public profiles at 10 of 10 accounts checked while finding zero
published email addresses — so LinkedIn is the one place the buyers were *observed*. Whether they
are observable and whether they are **reachable by publishing** are different claims, and only the
first is evidenced.

Impressions from other founders, agencies and developers would be a **false positive**: the number
goes up and the ICP is still absent. That is the failure mode to watch, and it is named here in
advance so a flattering total cannot be read as success later.

## What is being established

| Figure | Where it comes from | Why it is needed |
|---|---|---|
| Impressions per post | Post analytics | The denominator. Nothing is a rate without it |
| **Viewer job titles and companies** | Post analytics → top demographics | **The primary reading.** Whether the ICP is in the audience at all |
| Profile views per week | Profile analytics | Whether posts send anyone to look at who we are |
| Search appearances per week | Profile analytics | Whether the positioning is findable |
| Inbound conversations | DMs and comments | The only outcome that matters; expected to be zero for a while |
| Followers | Profile | Slow-moving, reported but never used as a success metric |

All of these are free on a standard account. None of them depends on LinkedIn Premium, and none of
them depends on Vercel Pro. Both open spend decisions stay open and neither blocks this.

## The unit of measurement is the post, and the sample minimum is 8

LinkedIn supplies the distribution, not us. One post reaching 40 people and another reaching 4,000
are not two readings of the same thing — the variance between posts is the algorithm's, not the
content's. So:

- The unit is the **post**, and nothing is read before **8 posts**.
- Report the **median** alongside the total. A single post that travels will otherwise define a
  "baseline" nothing else can reproduce, which is the week-shaped-artefact problem that set the
  owned-site window at four weeks.
- Expect a low floor early. A small network produces small numbers, and a small number here is
  **not** evidence the channel failed — it is evidence the window is not finished.

## Contamination, again

The owned-site window was corrupted by our own verification clicks, and the check that proved the
event fired was the same action that spoiled the measurement. The equivalents here:

1. **Our own profile views do not count.** LinkedIn does not show you your own view, but it does
   count views driven by us asking people to look. Anything solicited is recorded as solicited.
2. **Existing connections are not reach.** A post seen by people who already know us tests nothing
   about distribution. Where the demographics allow it, separate first-degree from beyond.
3. **Engagement pods, comment-for-comment and reciprocal likes are excluded outright.** They move
   impressions without moving audience, which makes the number worse than useless — it makes it
   confidently wrong.

## What this window decides

At 8 posts, one of three things is true:

- **The ICP is in the audience.** UK MSP and IT-services decision-makers appear in the viewer
  demographics with any regularity. Then a real experiment becomes possible and its thresholds come
  from these figures, not from a number anyone would like to see.
- **An audience exists but it is the wrong one.** Impressions are non-trivial and the ICP is absent.
  That is a **targeting** finding, not a content one, and the answer is who is being written for —
  not writing better.
- **There is no audience.** Impressions stay at the floor across all 8 posts. Then organic
  publishing on a cold profile does not reach this ICP either, and distribution remains unsolved
  after four measured channels. Say that plainly rather than posting a ninth time and hoping.

## What is not decided here

Nothing about the offer, the pricing or the message. None of those has been given a sample by any
channel yet, and this window will not give them one either — it measures whether anybody is on the
other end.

## Open, and needed from the founder

1. **Which profile.** The screen recorded "no measured presence"; whether an existing profile,
   network size and follower count exist is unknown to this repo and changes the expected floor.
2. **Cadence.** 8 posts is the minimum sample, not a schedule. Two a week reaches it in four weeks.
3. **The writing itself.** The cost of this channel is a person writing in their own voice
   repeatedly. That is the constraint to be honest about, and it is not one an agent removes.

Publishing is external surface. Nothing is posted by this document.
