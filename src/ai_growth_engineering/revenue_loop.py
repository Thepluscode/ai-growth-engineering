"""Deterministic commercial metrics, funnels, attribution and the money graph.

Everything here is arithmetic over effective funnel events. No model computes a canonical
metric: an interpretation layer may read these numbers and must never produce them.

A rate with a zero denominator is None, not 0 — "never asked" and "asked and refused" are
different findings. A cost metric with no spend recorded is None, not £0 — unrecorded spend
is not free acquisition.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, timedelta
from typing import Any, Iterable

from .execution import wilson
from .funnel_events import STAGE_OF

# name, numerator, denominator, multiplier, unit, definition — stored beside every value.
METRICS: tuple[tuple[str, str, str, int, str, str], ...] = (
    ("cpm", "spend_pence", "impression", 1000, "pence", "spend / impressions * 1000"),
    ("ctr", "click", "impression", 1, "rate", "clicks / impressions"),
    ("cpc", "spend_pence", "click", 1, "pence", "spend / clicks"),
    ("hook_rate_3s", "hook_view", "video_start", 1, "rate",
     "hook_view / video_start, where the adapter maps the platform's 3-second view to hook_view; "
     "platforms define hooks differently and no other definition is implied"),
    ("landing_page_cvr", "lead_created", "landing_page_view", 1, "rate", "leads / landing_page_views"),
    ("lead_cvr", "lead_created", "click", 1, "rate", "leads / clicks"),
    ("qualified_lead_rate", "lead_qualified", "lead_created", 1, "rate", "qualified_leads / leads"),
    ("accept_rate", "invitation_accepted", "invitation_sent", 1, "rate",
     "accepted invitations / invitations sent"),
    ("meaningful_reply_rate", "reply_meaningful", "delivered_messages", 1, "rate",
     "meaningful replies / delivered messages (a bounced send is an attempt, not a delivery)"),
    ("reply_rate", "reply_received", "delivered_messages", 1, "rate", "replies / delivered messages"),
    ("qualified_reply_rate", "reply_meaningful", "reply_received", 1, "rate",
     "qualified conversations / replies"),
    ("meeting_rate", "meeting_booked", "lead_qualified", 1, "rate", "meetings / qualified_leads"),
    ("reply_to_meeting_rate", "meeting_booked", "reply_meaningful", 1, "rate",
     "meetings / meaningful replies"),
    ("proposal_rate", "proposal_sent", "meeting_booked", 1, "rate", "proposals / meetings"),
    ("close_rate", "customer_won", "proposal_sent", 1, "rate", "customers / proposals"),
    ("cpl", "spend_pence", "lead_created", 1, "pence", "spend / leads"),
    ("qualified_cpl", "spend_pence", "lead_qualified", 1, "pence", "spend / qualified_leads"),
    ("cost_per_meeting", "spend_pence", "meeting_booked", 1, "pence", "spend / meetings"),
    ("cac", "spend_pence", "customer_won", 1, "pence",
     "acquisition spend recorded in scope / customers won in scope"),
    ("roas", "revenue_pence", "spend_pence", 1, "multiple", "revenue / spend"),
    ("pipeline_roas", "pipeline_pence", "spend_pence", 1, "multiple", "proposal value / spend"),
)

FUNNEL_PATHS: dict[str, tuple[str, ...]] = {
    "outbound": ("message_sent", "reply_meaningful", "meeting_booked", "proposal_sent",
                 "customer_won", "payment_received"),
    "invitation": ("invitation_sent", "invitation_accepted", "reply_meaningful", "meeting_booked",
                   "proposal_sent", "customer_won", "payment_received"),
    "paid": ("impression", "click", "lead_created", "lead_qualified", "meeting_booked",
             "proposal_sent", "customer_won", "payment_received"),
}

MODELS = ("first_touch", "last_touch", "linear")
TOUCH_TYPES = frozenset({"click", "landing_page_view", "message_sent", "invitation_sent", "lead_created"})


def dimension(event: dict, key: str) -> str:
    if key.startswith("metadata."):
        return str(event["metadata"].get(key[len("metadata."):], ""))
    return str(event.get(key) or "")


def filter_events(events: Iterable[dict], where: dict[str, str] | None = None, *,
                  since: str | None = None, until: str | None = None) -> list[dict]:
    """Slice by any event column or `metadata.<key>`, and by occurred_at date (inclusive)."""
    where = where or {}
    return [e for e in events
            if all(dimension(e, k) == v for k, v in where.items())
            and (since is None or e["occurred_at"][:10] >= since)
            and (until is None or e["occurred_at"][:10] <= until)]


def group_by(events: Iterable[dict], key: str) -> dict[str, list[dict]]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for event in events:
        groups[dimension(event, key)].append(event)
    return dict(groups)


def totals(events: Iterable[dict]) -> dict[str, Any]:
    events = list(events)
    currencies = {e["currency"] for e in events if e["value_pence"]}
    if len(currencies) > 1:
        raise ValueError(f"cannot total across currencies {sorted(currencies)}; slice by currency first")
    counts: Counter = Counter()
    money: Counter = Counter()
    for event in events:
        counts[event["event_type"]] += event["quantity"]
        money[event["event_type"]] += event["value_pence"]
    out: dict[str, Any] = dict(counts)
    out["spend_pence"] = money["spend_recorded"]
    out["revenue_pence"] = money["payment_received"] - money["refund"]
    out["pipeline_pence"] = money["proposal_sent"]
    out["spend_recorded"] = counts["spend_recorded"] > 0
    out["currency"] = next(iter(currencies), "")
    undelivered = undelivered_units(events)
    out["delivered_messages"] = sum(e["quantity"] for e in events if e["event_type"] == "message_sent"
                                    and (entity(e), e["experiment_id"]) not in undelivered)
    return out


def compute_metrics(events: Iterable[dict]) -> dict[str, Any]:
    t = totals(events)
    metrics = {}
    for name, numerator, denominator, multiplier, unit, definition in METRICS:
        n, d = t.get(numerator, 0), t.get(denominator, 0)
        if "spend_pence" in (numerator, denominator) and not t["spend_recorded"]:
            value, reason = None, "spend_not_recorded"
        elif not d:
            value, reason = None, "denominator_zero"
        else:
            raw = n * multiplier / d
            value, reason = (round(raw) if unit == "pence" else raw), None
        metrics[name] = {"metric": name, "value": value, "numerator": n, "denominator": d,
                         "unit": unit, "definition": definition, "reason": reason}
    return {"totals": t, "metrics": metrics}


def path_for(events: Iterable[dict]) -> str | None:
    t = totals(events)
    return next((name for name, steps in FUNNEL_PATHS.items() if t.get(steps[0], 0)), None)


def funnel(events: Iterable[dict], path: str) -> list[dict]:
    t = totals(events)
    steps, previous = [], None
    for event_type in FUNNEL_PATHS[path]:
        count = t.get(event_type, 0)
        base = t.get(previous, 0) if previous else 0
        steps.append({
            "event_type": event_type,
            "count": count,
            "conversion_from_previous": None if not base else count / base,
            "drop_off": None if not base else base - count,
            "cost_per_outcome_pence": (round(t["spend_pence"] / count)
                                       if t["spend_recorded"] and count else None),
        })
        previous = event_type
    return steps


# --- funnel diagnosis ----------------------------------------------------------------

# Every stage a buyer passes on the way to money, in order, per acquisition path.
LADDERS: dict[str, tuple[str, ...]] = {
    "invitation": ("invitation_sent", "invitation_accepted", "reply_received", "reply_meaningful",
                   "meeting_booked", "proposal_sent", "customer_won", "payment_received"),
    "outbound": ("message_sent", "reply_received", "reply_meaningful", "meeting_booked",
                 "proposal_sent", "customer_won", "payment_received"),
    "paid": ("impression", "click", "lead_created", "lead_qualified", "meeting_booked",
             "proposal_sent", "customer_won", "payment_received"),
}
STAGE_LABELS = {
    "invitation_sent": "Delivered", "message_sent": "Delivered", "invitation_accepted": "Accepted",
    "reply_received": "Replies", "reply_meaningful": "Qualified", "meeting_booked": "Meetings",
    "proposal_sent": "Proposals", "customer_won": "Customers", "payment_received": "Paid",
    "impression": "Impressions", "click": "Clicks", "lead_created": "Leads",
    "lead_qualified": "Qualified leads",
}
ATTEMPT_TYPES = frozenset({"invitation_undeliverable", "message_bounced"})
AGGREGATE_TYPES = frozenset({"impression", "click"})
# Outreach answers arrive days later, so a fresh exposure is not yet a refusal. Paid clicks and
# leads are immediate and carry no window.
WINDOWED_PATHS = frozenset({"invitation", "outbound"})
DEFAULT_RESPONSE_WINDOW_DAYS = 14
MIN_TRANSITION_SAMPLE = 30


def diagnose_funnel(events: Iterable[dict], path: str, *, as_of: str,
                    response_window_days: int = DEFAULT_RESPONSE_WINDOW_DAYS,
                    min_sample: int = MIN_TRANSITION_SAMPLE) -> dict:
    """Stage-by-stage commercial state of one acquisition path.

    A buyer counts at a stage when they reached it or any later one (a meeting implies a reply),
    but only if their exposure event exists: a downstream event with no exposure on this path is
    reported as unlinked and never counted. The first response transition uses only exposures
    older than the response window — an invitation sent yesterday is in flight, not declined.

    Transition status: NOT_REACHED (nothing upstream) · IN_FLIGHT (every exposure still inside
    the window) · INSUFFICIENT_DATA (denominator below min_sample) · MEASURED. Only a MEASURED
    transition may be called a leak; the largest constraint is still named, with its confidence.
    """
    events = list(events)
    ladder = LADDERS[path]
    position = {stage: i for i, stage in enumerate(ladder)}
    base = next(i for i, stage in enumerate(ladder) if stage not in AGGREGATE_TYPES)
    exposed_at: dict[str, str] = {}
    undelivered = undelivered_units(events)
    for e in events:
        if e["event_type"] == ladder[base] and entity(e) and (entity(e), e["experiment_id"]) not in undelivered:
            key = entity(e)
            exposed_at[key] = min(exposed_at.get(key, e["occurred_at"]), e["occurred_at"])
    furthest: dict[str, int] = {}
    observed_at_stage: dict[int, set[str]] = defaultdict(set)
    unlinked = 0
    for e in events:
        i = position.get(e["event_type"])
        if i is None or i <= base:
            continue
        key = entity(e)
        if key not in exposed_at:
            unlinked += 1
            continue
        furthest[key] = max(furthest.get(key, base), i)
        observed_at_stage[i].add(key)
    t = totals(events)
    windowed = path in WINDOWED_PATHS
    cutoff = (date.fromisoformat(as_of[:10]) - timedelta(days=response_window_days)).isoformat()
    matured = {k for k, at in exposed_at.items() if not windowed or at[:10] <= cutoff}

    def reached(i: int, pool: Iterable[str] | None = None) -> int:
        if ladder[i] in AGGREGATE_TYPES:
            return t.get(ladder[i], 0)
        return sum(1 for k in (exposed_at if pool is None else pool) if furthest.get(k, base) >= i)

    stages = []
    for i, stage in enumerate(ladder):
        count = reached(i)
        observed = (t.get(stage, 0) if stage in AGGREGATE_TYPES
                    else len(exposed_at) if i == base else len(observed_at_stage[i]))
        row: dict[str, Any] = {"stage": stage, "label": STAGE_LABELS[stage], "count": count,
                               "observed": observed, "transition": None}
        if i:
            response_step = windowed and i == base + 1
            numerator, denominator = ((reached(i, matured), len(matured)) if response_step
                                      else (count, reached(i - 1)))
            in_flight = len(exposed_at) - len(matured) if response_step else 0
            if denominator == 0:
                status = "IN_FLIGHT" if in_flight else "NOT_REACHED"
            elif denominator < min_sample:
                status = "INSUFFICIENT_DATA"
            else:
                status = "MEASURED"
            row["transition"] = {
                "from": ladder[i - 1], "to": stage, "numerator": numerator,
                "denominator": denominator, "rate": None if not denominator else numerator / denominator,
                "ci95": None if not denominator else wilson(numerator, denominator),
                "status": status, "in_flight": in_flight,
                "early_responses": count - numerator if response_step else 0,
            }
        stages.append(row)

    observed_transitions = [s for s in stages if s["transition"] and s["transition"]["denominator"]]
    constraint = None
    if observed_transitions:
        # The biggest MEASURABLE drop-off: a measured transition outranks an unmeasured one, then
        # the lowest rate, and a tie goes to the larger denominator (more evidence behind it).
        # ponytail: only the first response step is windowed; add per-stage windows once later
        # stages (acceptance -> reply, meeting -> proposal) carry enough volume to be misread.
        worst = min(observed_transitions,
                    key=lambda s: (s["transition"]["status"] != "MEASURED", s["transition"]["rate"],
                                   -s["transition"]["denominator"]))["transition"]
        n = worst["denominator"]
        confidence = "LOW" if n < min_sample else "MEDIUM" if n < 100 else "HIGH"
        upstream = STAGE_LABELS[worst["from"]].lower()
        constraint = {"from": worst["from"], "to": worst["to"], "rate": worst["rate"], "denominator": n,
                      "confidence": confidence, "is_leak": worst["status"] == "MEASURED",
                      "reason": (f"only {n} {upstream} observed" if confidence == "LOW"
                                 else f"{n} {upstream} observed")}
    return {
        "path": path, "as_of": as_of[:10],
        "response_window_days": response_window_days if windowed else None,
        "min_sample": min_sample, "stages": stages, "constraint": constraint,
        "insufficient": [s["stage"] for s in stages if s["transition"]
                         and s["transition"]["status"] in ("INSUFFICIENT_DATA", "IN_FLIGHT")],
        "attempts_not_exposure": sum(1 for e in events if e["event_type"] in ATTEMPT_TYPES),
        "unlinked_events": unlinked, "revenue_pence": t["revenue_pence"],
    }


# --- attribution ---------------------------------------------------------------------

def entity(event: dict) -> str:
    return (event.get("company") or event.get("person_id") or "").strip().lower()


def undelivered_units(events: Iterable[dict]) -> set[tuple[str, str]]:
    """(buyer, experiment) pairs whose outreach never arrived. A send followed by its bounce stays
    on record as an attempt, but it is not a delivered exposure and leaves every response denominator."""
    return {(entity(e), e["experiment_id"]) for e in events if e["event_type"] in ATTEMPT_TYPES}


def attribute(events: Iterable[dict], model: str = "linear") -> list[dict]:
    """One record per payment. Weights are explicit and amounts are whole pence that sum to
    the payment exactly; a payment with no prior touch is reported unattributed, not guessed."""
    if model not in MODELS:
        raise ValueError(f"model must be one of {MODELS}")
    events = list(events)
    touches_by: dict[str, list[dict]] = defaultdict(list)
    for event in events:
        if event["event_type"] in TOUCH_TYPES and entity(event):
            touches_by[entity(event)].append(event)
    records = []
    # ponytail: refunds are not attributed back to touches; add when a refund exists to test against.
    for payment in (e for e in events if e["event_type"] == "payment_received"):
        touches = [t for t in touches_by[entity(payment)] if t["occurred_at"] <= payment["occurred_at"]]
        n, amount = len(touches), payment["value_pence"]
        if n == 0:
            weights, shares = [], []
        elif model == "first_touch":
            weights, shares = [1.0] + [0.0] * (n - 1), [amount] + [0] * (n - 1)
        elif model == "last_touch":
            weights, shares = [0.0] * (n - 1) + [1.0], [0] * (n - 1) + [amount]
        else:
            weights, shares = [1 / n] * n, [amount // n] * n
            shares[-1] += amount - sum(shares)
        records.append({
            "revenue_event_id": payment["event_id"], "attribution_model": model,
            "entity": entity(payment), "amount_pence": amount, "currency": payment["currency"],
            "touchpoints": [{k: t[k] for k in ("event_id", "event_type", "occurred_at", "campaign_id",
                                               "creative_id", "experiment_id", "arm", "channel")}
                            for t in touches],
            "weights": weights, "attributed_pence": shares,
            "attributed_amount_pence": sum(shares), "unattributed_pence": amount - sum(shares),
        })
    return records


# --- money graph ---------------------------------------------------------------------

def money_graph_for_campaign(events: Iterable[dict], campaign_id: str) -> dict:
    events = list(events)
    scoped = [e for e in events if e["campaign_id"] == campaign_id]
    t = totals(scoped)
    touched = {entity(e) for e in scoped if entity(e)}
    # A buyer who paid is a customer whether or not anyone logged the win.
    customers = sorted({entity(e) for e in events if e["event_type"] in ("customer_won", "payment_received")
                        and entity(e) in touched})
    pipeline = sum(e["value_pence"] for e in events if e["event_type"] == "proposal_sent" and entity(e) in touched)
    attributed = {model: sum(share for record in attribute(events, model)
                             for touch, share in zip(record["touchpoints"], record["attributed_pence"])
                             if touch["campaign_id"] == campaign_id)
                  for model in MODELS}
    spend = t["spend_pence"] if t["spend_recorded"] else None
    return {
        "campaign_id": campaign_id, "spend_pence": spend, "pipeline_pence": pipeline,
        "customers": customers, "attributed_revenue_pence": attributed,
        "roas": {m: (None if not spend else attributed[m] / spend) for m in MODELS},
        "cac_pence": None if spend is None or not customers else round(spend / len(customers)),
    }


def money_graph_for_entity(events: Iterable[dict], name: str) -> dict:
    """Trace one buyer from every touch to every pound, with the model used for attribution."""
    events = list(events)
    key = name.strip().lower()
    chain = [e for e in events if entity(e) == key]
    campaigns = sorted({e["campaign_id"] for e in chain if e["campaign_id"]})
    return {
        "entity": key,
        "chain": [{"occurred_at": e["occurred_at"], "stage": STAGE_OF.get(e["event_type"], ""),
                   "event_type": e["event_type"], "event_id": e["event_id"],
                   "campaign_id": e["campaign_id"], "creative_id": e["creative_id"],
                   "experiment_id": e["experiment_id"], "arm": e["arm"], "channel": e["channel"],
                   "value_pence": e["value_pence"], "provenance": e["provenance"]} for e in chain],
        "revenue_pence": totals(chain)["revenue_pence"],
        "campaigns": campaigns,
        "experiments": sorted({(e["experiment_id"], e["arm"]) for e in chain if e["experiment_id"]}),
        "attribution": {m: [r for r in attribute(events, m) if r["entity"] == key] for m in MODELS},
        "campaign_cac_pence": {c: money_graph_for_campaign(events, c)["cac_pence"] for c in campaigns},
    }
