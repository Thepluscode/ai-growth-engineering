"""Segment performance and target / offer / route decisioning.

Aggregates what already exists — funnel events, campaigns, offers, audiences, buyer truth — one
dimension at a time, and compares segments under one explicit evidence policy. A buyer belongs to
the segment of their first exposure. A recommendation appears only when the policy allows it;
NOT_ENOUGH_EVIDENCE and NOT_COMPARABLE are normal answers, not failures.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, timedelta

from . import registries
from .buyer_truth import PROBLEM_CATEGORIES, _themes, buyer_evidence, scope, willingness_to_pay
from .revenue_loop import compute_metrics, entity, totals

# Every threshold a verdict depends on. Change a number here and every verdict changes with it.
EVIDENCE_POLICY = {
    "response_window_days": 14,
    "rate_min_denominator": 30,
    # A segment's state. Sample counts buyers whose first delivery is older than the response window.
    "DESCRIPTIVE": {"matured_delivered": 30, "organisations": 10, "downstream_organisations": 0},
    "DECISION_WORTHY": {"matured_delivered": 100, "organisations": 30, "downstream_organisations": 5},
    # A leader is recommended only with this many organisations at qualified conversation or beyond.
    "recommend_min_downstream_organisations": 3,
    # A buyer-truth theme is a segment's "top" only when this many organisations stated it.
    "theme_min_organisations": 2,
}
STATES = ("NO_DATA", "EARLY_SIGNAL", "DESCRIPTIVE", "DECISION_WORTHY")
RANK = {state: i for i, state in enumerate(STATES)}
UNKNOWN = "UNKNOWN"
UNRESOLVED = ("NOT_ENOUGH_EVIDENCE", "NOT_COMPARABLE")

DIMENSIONS = ("icp", "buyer_role", "audience_type", "offer", "price", "campaign", "experiment", "channel",
              "recipient_route", "acquisition_route")
# Asked for, but carried by no source record yet: listed, never guessed.
NOT_RECORDED = ("company_type", "company_size", "geography", "buyer_seniority")
ATTEMPTS = frozenset({"message_sent", "message_bounced", "invitation_sent", "invitation_undeliverable"})
DELIVERED = frozenset({"message_sent", "invitation_sent"})
# A later stage implies the earlier ones within this chain (a meeting implies a conversation).
IMPLIED = (("replies", {"reply_received"}), ("qualified_replies", {"reply_meaningful", "lead_qualified"}),
           ("meetings", {"meeting_booked", "meeting_held"}), ("proposals", {"proposal_sent", "proposal_accepted"}))
DIRECT = (("accepted_proposals", {"proposal_accepted"}), ("customers", {"customer_won", "payment_received"}),
          ("payments", {"payment_received"}))
# Commercial outcomes, nearest money first. More replies never outranks more customers.
HIERARCHY = ("observed_revenue_pence", "customers", "accepted_proposals", "proposals", "meetings",
             "qualified_replies", "replies", "accepted", "delivered")
ACCESS_KEYS = frozenset({"accepted", "delivered"})
CONFOUND_ATTRIBUTES = ("experiment", "offer", "icp", "audience_type", "channel", "recipient_route")
INHERENT = {"acquisition_route": {"channel", "recipient_route"}, "price": {"offer"}}
BLOCKS_OFFER_COMPARISON = frozenset({"experiment", "channel", "recipient_route", "period", "cross_experiment"})
SPEND_FIELDS = {"experiment": "experiment_id", "campaign": "campaign_id", "channel": "channel", "icp": "icp",
                "offer": "offer_id"}
ECONOMICS = ("cpl", "qualified_cpl", "cost_per_meeting", "cac", "roas", "pipeline_roas")
TRUTH_SECTIONS = (
    ("problems", PROBLEM_CATEGORIES), ("objections", frozenset({"OBJECTION"})),
    ("buying_criteria", frozenset({"BUYING_CRITERION"})), ("authority_signals", frozenset({"AUTHORITY_SIGNAL"})),
    ("budget_signals", frozenset({"BUDGET_SIGNAL"})), ("reasons_for_rejection", frozenset({"REASON_FOR_REJECTION"})),
    ("reasons_for_purchase", frozenset({"REASON_FOR_PURCHASE"})),
)
TARGET_DIMENSIONS = ("icp", "buyer_role", "audience_type")


def _money(pence: int | float) -> str:
    return f"£{pence / 100:,.2f}"


def load_registry(db_path: str) -> dict:
    return {name: {row[registries.REGISTRIES[name][0]]: row for row in registries.rows(db_path, name)}
            for name in ("campaigns", "offers", "audiences")}


def _attributes(event: dict, registry: dict) -> dict:
    meta = event["metadata"] or {}
    campaign = registry["campaigns"].get(event["campaign_id"]) or {}
    offer = registry["offers"].get(campaign.get("offer_id", "")) or {}
    # An invitation is addressed to one named person's own profile; a send records its recipient class.
    route = meta.get("recipient_class") or ("named_buyer_connection" if event["event_type"].startswith("invitation") else "")
    values = {
        "experiment": event["experiment_id"], "campaign": event["campaign_id"], "channel": event["channel"],
        "recipient_route": route,
        "acquisition_route": f"{event['channel'] or UNKNOWN}/{route or UNKNOWN}" if event["channel"] or route else "",
        "icp": campaign.get("icp", ""), "offer": campaign.get("offer_id", ""),
        # A price of 0 is how an unpriced offer is stored, so it is unknown, not free.
        "price": _money(offer["price_pence"]) if offer.get("price_pence") else "",
        "audience_type": (registry["audiences"].get(campaign.get("audience_id", "")) or {}).get("audience_type", ""),
        "buyer_role": meta.get("role", ""),
    }
    return {key: value or UNKNOWN for key, value in values.items()}


def _rate(numerator: int, denominator: int) -> dict:
    if denominator == 0:
        return {"value": None, "numerator": numerator, "denominator": 0, "status": "NOT_DERIVABLE"}
    return {"value": numerator / denominator, "numerator": numerator, "denominator": denominator,
            "status": "MEASURED" if denominator >= EVIDENCE_POLICY["rate_min_denominator"] else "INSUFFICIENT_DATA"}


def _state(counts: dict, *, with_downstream: bool) -> str:
    if counts["delivered"] == 0:
        return "NO_DATA"
    downstream = max(counts["qualified_replies"], counts["customers"])
    for state in ("DECISION_WORTHY", "DESCRIPTIVE"):
        rule = EVIDENCE_POLICY[state]
        if (counts["matured_delivered"] >= rule["matured_delivered"]
                and counts.get("organisations", counts["exposures"]) >= rule["organisations"]
                and (not with_downstream or downstream >= rule["downstream_organisations"])):
            return state
    return "EARLY_SIGNAL"


def evidence_state(counts: dict) -> str:
    """Sample and downstream outcomes: what a leading segment must reach."""
    return _state(counts, with_downstream=True)


def sample_state(counts: dict) -> str:
    """Sample only: what the segment it is compared against must reach. A segment that nobody
    answered can still be a well-measured zero."""
    return _state(counts, with_downstream=False)


def _economics(value: str, dimension: str, events: list[dict], scoped: list[dict], registry: dict) -> dict:
    if dimension not in SPEND_FIELDS:
        return {name: {"value": None, "status": "NOT_DERIVABLE",
                       "reason": f"spend is recorded per campaign, not per {dimension}"} for name in ECONOMICS}
    field = SPEND_FIELDS[dimension]
    spend = [e for e in scoped if e["event_type"] == "spend_recorded"
             and str((registry["campaigns"].get(e["campaign_id"]) or {}).get(field) or UNKNOWN) == value]
    metrics = compute_metrics(events + spend)["metrics"]
    return {name: {"value": metrics[name]["value"],
                   "status": "NOT_DERIVABLE" if metrics[name]["value"] is None else "DERIVED",
                   "reason": metrics[name].get("reason", "")} for name in ECONOMICS}


def _segment_truth(evidence: list[dict], units: set[tuple[str, str]], events: list[dict]) -> dict | None:
    buyers = {buyer for buyer, _ in units}
    # Evidence tagged to an experiment belongs to that experiment's exposure; untagged evidence to the buyer.
    mine = [i for i in evidence
            if (i["buyer"], i["experiment_id"]) in units or (not i["experiment_id"] and i["buyer"] in buyers)]
    if not mine:
        return None
    truth: dict = {}
    for name, categories in TRUTH_SECTIONS:
        items = [i for i in mine if i["category"] in categories]
        if not items:
            continue
        themes = sorted(({"theme": theme, "organisations": scope(group)["organisations"] or len({i["buyer"] for i in group}),
                          "evidence_ids": sorted({i["evidence_id"] for i in group})}
                         for theme, group in _themes(items, categories).items()),
                        key=lambda t: (-t["organisations"], t["theme"]))
        truth[name] = {"organisations": len({i["buyer"] for i in items}),
                       "evidence_ids": sorted({i["evidence_id"] for i in items}), "themes": themes,
                       "top": next((t for t in themes if t["organisations"] >= EVIDENCE_POLICY["theme_min_organisations"]), None)}
    ladder = Counter(willingness_to_pay(events, evidence, buyer)["strongest"] for buyer in buyers)
    truth["willingness_to_pay"] = {rung: count for rung, count in ladder.items() if rung}
    return truth


def _units(events: list[dict]) -> tuple[dict, dict, int]:
    """Exposure units: one per (buyer, experiment). One experiment's sends never absorb another's.
    An outcome whose experiment never exposed the buyer — or that names no experiment — goes to the
    buyer's most recent exposure before it (the earliest, if none precedes it)."""
    ordered = sorted((e for e in events if entity(e)), key=lambda e: (e["occurred_at"], e["event_id"]))
    first: dict[tuple[str, str], dict] = {}
    for e in ordered:
        if e["event_type"] in ATTEMPTS:
            first.setdefault((entity(e), e["experiment_id"]), e)
    starts: dict[str, list] = defaultdict(list)
    for unit, e in first.items():
        starts[unit[0]].append((e["occurred_at"], unit))
    by_unit: dict[tuple[str, str], list[dict]] = defaultdict(list)
    reassigned = 0
    for e in ordered:
        own = (entity(e), e["experiment_id"])
        if own in first:
            by_unit[own].append(e)
        elif starts.get(entity(e)):
            timeline = sorted(starts[entity(e)])
            prior = [unit for at, unit in timeline if at <= e["occurred_at"]]
            by_unit[prior[-1] if prior else timeline[0][1]].append(e)
            reassigned += bool(e["experiment_id"])
    return first, by_unit, reassigned


def _segment(value: str, keys: set[tuple[str, str]], by_entity: dict, first: dict, evidence: list[dict],
             cutoff: str, dimension: str, scoped: list[dict], registry: dict) -> dict:
    types = {k: {e["event_type"] for e in by_entity[k]} for k in keys}
    # A send whose bounce is recorded was attempted, not delivered.
    delivered = {k for k in keys if types[k] & DELIVERED and not types[k] & (ATTEMPTS - DELIVERED)}
    first_delivery = {k: min(e["occurred_at"] for e in by_entity[k] if e["event_type"] in DELIVERED) for k in delivered}
    matured = {k for k, at in first_delivery.items() if at[:10] <= cutoff}
    reached: dict[str, set[str]] = {}
    for i, (name, _) in enumerate(IMPLIED):
        later = set().union(*(stage for _, stage in IMPLIED[i:]))
        reached[name] = {k for k in keys if types[k] & later}
    invited = {k for k in delivered if "invitation_sent" in types[k]}
    reached["accepted"] = {k for k in invited if "invitation_accepted" in types[k] or k in reached["replies"]}
    for name, stage in DIRECT:
        reached[name] = {k for k in keys if types[k] & stage}
    events = [e for k in keys for e in by_entity[k]]
    money = totals([e for e in events if e["event_type"] in ("payment_received", "refund", "proposal_sent")])
    counts = {"exposures": len(keys), "organisations": len({buyer for buyer, _ in keys}),
              "delivered": len(delivered), "matured_delivered": len(matured),
              **{name: len(members) for name, members in reached.items()},
              "observed_revenue_pence": money["revenue_pence"], "pipeline_pence": money["pipeline_pence"]}
    delivered_at = sorted(first_delivery.values())
    return {
        "value": value, "counts": counts,
        "rates": {
            "delivery_rate": _rate(len(delivered), len(keys)),
            "acceptance_rate": _rate(len(reached["accepted"] & matured), len(invited & matured)),
            "reply_rate": _rate(len(reached["replies"] & matured), len(matured)),
            "qualified_reply_rate": _rate(counts["qualified_replies"], counts["replies"]),
            "meeting_rate": _rate(counts["meetings"], counts["qualified_replies"]),
            "proposal_rate": _rate(counts["proposals"], counts["meetings"]),
            "close_rate": _rate(counts["customers"], counts["proposals"]),
        },
        "economics": _economics(value, dimension, events, scoped, registry),
        "state": evidence_state(counts), "sample_state": sample_state(counts),
        "attributes": {a: sorted({first[k][a] for k in keys}) for a in CONFOUND_ATTRIBUTES},
        "period": [delivered_at[0][:10], delivered_at[-1][:10]] if delivered_at else [],
        "buyer_truth": _segment_truth(evidence, keys, events),
    }


def segment_performance(events: list[dict], evidence: list[dict], dimension: str, *, as_of: str, registry: dict,
                        experiment_id: str | None = None, units: set[tuple[str, str]] | None = None) -> dict:
    if dimension not in DIMENSIONS:
        raise ValueError(f"{dimension!r} is not a recorded dimension; recorded: {DIMENSIONS}; "
                         f"not recorded: {NOT_RECORDED}")
    scoped = [e for e in events if not experiment_id or e["experiment_id"] == experiment_id]
    exposures, by_unit, reassigned = _units(scoped)
    if units is not None:
        exposures = {u: e for u, e in exposures.items() if u in units}
    first = {unit: _attributes(e, registry) for unit, e in exposures.items()}
    members: dict[str, set] = defaultdict(set)
    spread: dict[str, set] = defaultdict(set)
    for unit, attrs in first.items():
        members[attrs[dimension]].add(unit)
        spread[unit[0]].add(attrs[dimension])
    cutoff = (date.fromisoformat(as_of[:10]) - timedelta(days=EVIDENCE_POLICY["response_window_days"])).isoformat()
    experiments = sorted({attrs["experiment"] for attrs in first.values()} - {UNKNOWN})
    segments = [_segment(value, keys, by_unit, first, evidence, cutoff, dimension, scoped, registry)
                for value, keys in members.items()]
    return {
        "dimension": dimension, "as_of": as_of[:10], "experiment_scope": experiment_id or "ALL",
        "cross_experiment": not experiment_id and len(experiments) > 1, "experiments": experiments,
        "overlapping_buyers": sum(1 for values in spread.values() if len(values) > 1),
        "outcomes_reassigned": reassigned,
        "unexposed_buyers": len({entity(e) for e in scoped if entity(e)} - {buyer for buyer, _ in first}),
        "not_recorded_dimensions": list(NOT_RECORDED),
        "segments": sorted(segments, key=lambda s: tuple(-s["counts"][k] for k in HIERARCHY) + (s["value"],)),
    }


def _confounds(ranked: list[dict], performance: dict) -> list[dict]:
    dimension = performance["dimension"]
    skip = {dimension} | INHERENT.get(dimension, set())
    found = []
    for attr in CONFOUND_ATTRIBUTES:
        if attr in skip or len(ranked) < 2:
            continue
        if len({tuple(s["attributes"][attr]) for s in ranked}) > 1:
            found.append({"attribute": attr, "detail": f"segments differ in {attr}: " + "; ".join(
                f"{s['value']} = {', '.join(s['attributes'][attr])}" for s in ranked)})
    periods = [s["period"] for s in ranked if s["period"]]
    if any(a[1] < b[0] or b[1] < a[0] for i, a in enumerate(periods) for b in periods[i + 1:]):
        found.append({"attribute": "period", "detail": "observation periods do not overlap: " + "; ".join(
            f"{s['value']} {s['period'][0]}..{s['period'][1]}" for s in ranked if s["period"])})
    if performance["cross_experiment"]:
        found.append({"attribute": "cross_experiment", "detail": "descriptive cross-experiment analysis across "
                      f"{', '.join(performance['experiments'])}: outcomes are shown side by side, not as one test"})
    if performance["overlapping_buyers"]:
        found.append({"attribute": "overlap", "detail": f"{performance['overlapping_buyers']} buyer(s) appear in more "
                      f"than one {dimension} segment: each experiment's exposure counts in its own segment, and an "
                      "outcome without its own exposure goes to the buyer's most recent prior exposure"})
    return found


def _show(key: str, value: int) -> str:
    return _money(value) if key.endswith("_pence") else str(value)


def _verdict(ranked: list[dict], confounds: list[dict]) -> dict:
    if len(ranked) < 2:
        return {"state": "NOT_ENOUGH_EVIDENCE",
                "reason": f"only one segment observed ({ranked[0]['value']}): nothing to compare" if ranked else "no segment observed"}
    lead, runner = ranked[0], ranked[1]
    decisive = next((k for k in HIERARCHY if lead["counts"][k] != runner["counts"][k]), None)
    if decisive is None:
        return {"state": "NOT_ENOUGH_EVIDENCE", "reason": "the leading segments are tied on every observed outcome"}
    a, b = _show(decisive, lead["counts"][decisive]), _show(decisive, runner["counts"][decisive])
    if decisive in ACCESS_KEYS:
        return {"state": "NOT_ENOUGH_EVIDENCE", "reason": f"{lead['value']} and {runner['value']} differ only in access "
                f"({decisive} {a} vs {b}), not in any commercial outcome"}
    strength = STATES[min(RANK[lead["state"]], RANK[runner["sample_state"]])]
    if RANK[strength] < RANK["DESCRIPTIVE"]:
        return {"state": "NOT_ENOUGH_EVIDENCE", "reason": f"{lead['value']} leads on {decisive} ({a} vs {b}), but the "
                f"evidence is {strength}; the policy needs DESCRIPTIVE for both segments"}
    blocked = strength == "DECISION_WORTHY" and bool(confounds)
    return {"state": "DECISION" if strength == "DECISION_WORTHY" and not confounds else "DESCRIPTIVE_LEAD",
            "leader": lead["value"], "runner_up": runner["value"], "decided_on": decisive, "strength": strength,
            "statement": f"Observed commercial performance currently favours {lead['value']} on "
                         f"{decisive.replace('_', ' ')} ({a} vs {b}).",
            "reason": "decision-worthy sample, but confounded" if blocked else ""}


def compare_segments(performance: dict) -> dict:
    ranked = [s for s in performance["segments"] if s["value"] != UNKNOWN]
    confounds = _confounds(ranked, performance)
    return {**performance, "ranked": [s["value"] for s in ranked], "confounds": confounds,
            "verdict": _verdict(ranked, confounds),
            "best_early_signal": next((s for s in ranked if s["counts"]["qualified_replies"] or s["counts"]["customers"]), None)}


def _summary(segment: dict) -> dict:
    return {"value": segment["value"], "state": segment["state"],
            **{k: segment["counts"][k] for k in ("delivered", "matured_delivered", "accepted", "replies",
                                                 "qualified_replies", "meetings", "proposals", "customers",
                                                 "observed_revenue_pence")},
            "reply_rate": segment["rates"]["reply_rate"], "buyer_truth": segment["buyer_truth"]}


def _leader(comparison: dict) -> dict | None:
    verdict = comparison["verdict"]
    if verdict["state"] not in ("DECISION", "DESCRIPTIVE_LEAD"):
        return None
    lead = next(s for s in comparison["segments"] if s["value"] == verdict["leader"])
    return lead if lead["counts"]["qualified_replies"] >= EVIDENCE_POLICY["recommend_min_downstream_organisations"] else None


def _uncertainty(verdict: dict, lead: dict) -> str:
    if verdict["state"] == "DESCRIPTIVE_LEAD":
        rule = EVIDENCE_POLICY["DECISION_WORTHY"]
        return (f"Whether the lead on {verdict['decided_on'].replace('_', ' ')} survives at decision-worthy exposure "
                f"({rule['matured_delivered']} matured deliveries, {rule['organisations']} organisations, "
                f"{rule['downstream_organisations']} downstream organisations).")
    if lead["counts"]["customers"] < 2:
        return "Whether a second customer in this segment pays."
    return "Whether the advantage holds on revenue per customer, not only on customer count."


def _decision(dimension: str, comparison: dict, lead: dict) -> dict:
    verdict = comparison["verdict"]
    return {"recommended": lead["value"], "dimension": dimension, "why": verdict["statement"],
            "buyer_truth": lead["buyer_truth"],
            "commercial_performance": {k: lead["counts"][k] for k in ("delivered", "qualified_replies", "meetings",
                                                                     "proposals", "customers", "observed_revenue_pence")},
            "evidence_strength": verdict["strength"], "confounds": comparison["confounds"],
            "main_uncertainty": _uncertainty(verdict, lead), "comparison": comparison}


def _unresolved(state: str, reason: str, segments: list[dict], uncertainty: str, **extra) -> dict:
    strongest = max((s["state"] for s in segments), key=RANK.get, default="NO_DATA")
    return {"recommended": state, "reason": reason, "evidence_strength": strongest,
            "main_uncertainty": uncertainty, **extra}


def _context(db_path: str, as_of: str | None, events: list[dict] | None, evidence: list[dict] | None):
    from .marketing_engineer import linked_events

    return (as_of or date.today().isoformat(), linked_events(db_path) if events is None else events,
            buyer_evidence(db_path) if evidence is None else evidence, load_registry(db_path))


def recommend_target_segment(db_path: str, *, as_of: str | None = None, events: list[dict] | None = None,
                             evidence: list[dict] | None = None) -> dict:
    as_of, events, evidence, registry = _context(db_path, as_of, events, evidence)
    comparisons = {d: compare_segments(segment_performance(events, evidence, d, as_of=as_of, registry=registry))
                   for d in TARGET_DIMENSIONS}
    for dimension, comparison in comparisons.items():
        lead = _leader(comparison)
        if lead:
            return _decision(dimension, comparison, lead)
    # A signal only means something against an alternative: prefer a dimension with two or more segments.
    early = next((c["best_early_signal"] for c in sorted(comparisons.values(), key=lambda c: len(c["ranked"]) < 2)
                  if c["best_early_signal"]), None)
    return _unresolved(
        "NOT_ENOUGH_EVIDENCE",
        "; ".join(f"{d}: {c['verdict'].get('reason') or c['verdict'].get('statement')}" for d, c in comparisons.items()),
        [s for c in comparisons.values() for s in c["segments"]],
        "Which buyer segment converts: no target comparison meets the evidence policy yet.",
        best_early_signal=early and _summary(early), comparisons=comparisons)


def unit_attributes(events: list[dict], registry: dict) -> dict[tuple[str, str], dict]:
    return {unit: _attributes(e, registry) for unit, e in _units(events)[0].items()}


def recommend_offer(db_path: str, *, as_of: str | None = None, events: list[dict] | None = None,
                    evidence: list[dict] | None = None) -> dict:
    """Compare offers only among buyers in the same context (ICP and audience type). An offer
    shown to a different audience is NOT_COMPARABLE: the difference would be the audience."""
    as_of, events, evidence, registry = _context(db_path, as_of, events, evidence)
    overall = segment_performance(events, evidence, "offer", as_of=as_of, registry=registry)
    offers = [s for s in overall["segments"] if s["value"] != UNKNOWN]
    base = {"offers": [_summary(s) for s in offers]}
    uncertainty = "Which offer converts within one buyer context."
    if len(offers) < 2:
        return _unresolved("NOT_ENOUGH_EVIDENCE", f"only one offer observed ({offers[0]['value']})" if offers
                           else "no offer observed", offers, uncertainty, **base)
    contexts: dict[tuple, dict[str, set]] = defaultdict(lambda: defaultdict(set))
    for unit, attrs in unit_attributes(events, registry).items():
        if attrs["offer"] != UNKNOWN:
            contexts[(attrs["icp"], attrs["audience_type"])][attrs["offer"]].add(unit)
    shared = {ctx: by_offer for ctx, by_offer in contexts.items() if len(by_offer) >= 2}
    if not shared:
        return _unresolved("NOT_COMPARABLE", "no buyer context (ICP, audience type) saw more than one offer: any "
                           "difference is the audience, not the offer", offers, uncertainty, **base)
    context, by_offer = max(shared.items(), key=lambda item: (sum(len(b) for b in item[1].values()), item[0]))
    comparison = compare_segments(segment_performance(events, evidence, "offer", as_of=as_of, registry=registry,
                                                      units=set().union(*by_offer.values())))
    where = {"icp": context[0], "audience_type": context[1]}
    blocking = [c["detail"] for c in comparison["confounds"] if c["attribute"] in BLOCKS_OFFER_COMPARISON]
    if blocking:
        return _unresolved("NOT_COMPARABLE", "offer differences are confounded: " + "; ".join(blocking),
                           comparison["segments"], uncertainty, context=where, comparison=comparison, **base)
    lead = _leader(comparison)
    if lead is None:
        return _unresolved("NOT_ENOUGH_EVIDENCE", comparison["verdict"].get("reason") or "leader below the downstream minimum",
                           comparison["segments"], uncertainty, context=where, comparison=comparison, **base)
    return {**_decision("offer", comparison, lead), "context": where, **base}


def recommend_acquisition_route(db_path: str, *, as_of: str | None = None, events: list[dict] | None = None,
                                evidence: list[dict] | None = None) -> dict:
    """Channel and recipient route kept apart, compared together as the route a buyer was reached by.
    Access (delivery, acceptance) never wins against downstream evidence."""
    as_of, events, evidence, registry = _context(db_path, as_of, events, evidence)
    comparison = compare_segments(segment_performance(events, evidence, "acquisition_route", as_of=as_of, registry=registry))
    routes = [s for s in comparison["segments"] if s["value"] != UNKNOWN]

    def access(segment: dict) -> float | None:
        return next((segment["rates"][r]["value"] for r in ("acceptance_rate", "delivery_rate")
                     if segment["rates"][r]["value"] is not None), None)

    access_leader = max((s for s in routes if access(s) is not None), key=access, default=None)
    downstream_leader = comparison["verdict"].get("leader")
    contradiction = None
    if access_leader and downstream_leader and access_leader["value"] != downstream_leader:
        contradiction = (f"{access_leader['value']} leads on access ({access(access_leader):.0%}) but {downstream_leader} "
                         "leads on commercial outcomes; access is not optimised against downstream evidence")
    base = {
        "routes": [{**_summary(s), "access_rate": access(s)} for s in routes],
        "access_vs_downstream": contradiction,
        "no_reply_at_measured_sample": [
            f"{s['value']}: {s['rates']['reply_rate']['numerator']}/{s['rates']['reply_rate']['denominator']} replies ({s['state']})"
            for s in routes if s["rates"]["reply_rate"]["status"] == "MEASURED" and s["counts"]["replies"] == 0],
        "channel_verdict": compare_segments(segment_performance(events, evidence, "channel", as_of=as_of, registry=registry))["verdict"],
        "recipient_route_verdict": compare_segments(segment_performance(events, evidence, "recipient_route", as_of=as_of,
                                                                        registry=registry))["verdict"],
    }
    lead = _leader(comparison)
    if lead:
        return {**_decision("acquisition_route", comparison, lead), **base}
    return _unresolved("NOT_ENOUGH_EVIDENCE", comparison["verdict"].get("reason") or "leader below the downstream minimum",
                       routes, "Which route reaches buyers who go on to talk, meet and buy.", comparison=comparison, **base)


def decision_summary(db_path: str, *, as_of: str, events: list[dict], evidence: list[dict]) -> dict | None:
    """None when nothing has been delivered, so the status page never shows an empty ranking."""
    if not any(e["event_type"] in DELIVERED for e in events):
        return None
    kwargs = {"as_of": as_of, "events": events, "evidence": evidence}
    return {"target": recommend_target_segment(db_path, **kwargs), "offer": recommend_offer(db_path, **kwargs),
            "route": recommend_acquisition_route(db_path, **kwargs)}


def segment_proposal(decisions: dict, history: list[dict]) -> dict | None:
    """One test from segment evidence, nearest revenue first: offer, then route, then whether a
    descriptive segment lead survives more exposure."""
    target, offer, route = decisions["target"], decisions["offer"], decisions["route"]
    rule = EVIDENCE_POLICY["DECISION_WORTHY"]

    def clear(decision: dict) -> bool:
        return decision["recommended"] not in UNRESOLVED and decision.get("evidence_strength") == "DECISION_WORTHY"

    def proposal(variable: str, hypothesis: str, control: str, variant: str, metric: str, why: str) -> dict:
        return {
            "status": "PROPOSED_NEEDS_CONTRACT", "experiment_id": None, "based_on_experiment_id": None,
            "hypothesis": hypothesis, "single_variable": variable, "control": control, "variant": variant,
            "icp": target["recommended"] if target["recommended"] not in UNRESOLVED else "carried over",
            "offer": "the variable under test" if variable == "offer" else "carried over",
            "channel": "carried over", "primary_metric": metric,
            "guardrails": ["declare before exposure (experiment_trust_guardrails)"],
            "sample_and_stopping_rule": f"per arm: {rule['matured_delivered']} matured deliveries, {rule['organisations']} "
                                        f"organisations, evaluated whole (EVIDENCE_POLICY.DECISION_WORTHY)",
            "why_highest_value": why, "evidence": [target.get("why") or target.get("reason", "")],
            "previous_experiments": history,
            "stop_condition": f"If {metric} does not differ once both arms meet the policy, {variable} is not the "
                              "constraint: stop and return to the next uncertainty nearer revenue.",
        }

    if clear(target) and not clear(offer):
        metric = "close_rate" if target["commercial_performance"]["proposals"] else "qualified_reply_rate"
        return proposal("offer", f"Within {target['dimension']} = {target['recommended']}, changing only the offer raises {metric}.",
                        "the offer this segment has already seen",
                        "not written: the operator writes one alternative offer; the engine does not invent terms or prices",
                        metric, f"The target is decision-worthy ({target['why']}) but the offer is {offer['recommended']}: "
                        f"{offer.get('reason', '')}. The offer sits nearer revenue than the route.")
    if clear(target) and clear(offer) and not clear(route):
        return proposal("recipient_route", f"For {target['recommended']} with {offer['recommended']}, changing only the "
                        "recipient route raises the qualified reply rate.", "the route this segment was reached by",
                        "not written: the operator names one alternative route", "qualified_reply_rate",
                        f"Target and offer are decision-worthy; the route is {route['recommended']}: {route.get('reason', '')}.")
    if target["recommended"] not in UNRESOLVED and target["commercial_performance"]["customers"] == 0:
        verdict = target["comparison"]["verdict"]
        return proposal("audience", f"The {target['recommended']} lead on {verdict['decided_on'].replace('_', ' ')} survives "
                        "at decision-worthy exposure.", f"{target['dimension']} = {verdict['runner_up']}",
                        f"{target['dimension']} = {target['recommended']}", "qualified_reply_rate",
                        f"{verdict['statement']} The evidence is {target['evidence_strength']} and no customer has come from it yet.")
    return None


def _fmt_rate(rate: dict) -> str:
    if rate["value"] is None:
        return rate["status"]
    return f"{rate['value']:.1%} ({rate['numerator']}/{rate['denominator']})" + (
        "" if rate["status"] == "MEASURED" else f" {rate['status']}")


def _fmt_economic(name: str, metric: dict) -> str:
    if metric["value"] is None:
        return f"{name} {metric['status']}"
    return f"{name} {metric['value']:.2f}x" if "roas" in name else f"{name} {_money(round(metric['value']))}"


def render_segments(comparison: dict) -> str:
    head = f"SEGMENTS by {comparison['dimension']} · scope {comparison['experiment_scope']} · as of {comparison['as_of']}"
    lines = [head + (" · DESCRIPTIVE CROSS-EXPERIMENT ANALYSIS" if comparison["cross_experiment"] else "")]
    for s in comparison["segments"]:
        k = s["counts"]
        lines += [f"  {s['value']}  [{s['state']}]",
                  f"    exposures {k['exposures']} · delivered {k['delivered']} (matured {k['matured_delivered']}) · accepted "
                  f"{k['accepted']} · replies {k['replies']} · qualified {k['qualified_replies']} · meetings {k['meetings']} · "
                  f"proposals {k['proposals']} · customers {k['customers']} · revenue {_money(k['observed_revenue_pence'])} · "
                  f"pipeline {_money(k['pipeline_pence'])}",
                  "    rates: " + " · ".join(f"{n.removesuffix('_rate')} {_fmt_rate(r)}" for n, r in s["rates"].items()),
                  "    economics: " + " · ".join(_fmt_economic(n, m) for n, m in s["economics"].items())]
        for name, section in (s["buyer_truth"] or {}).items():
            if name == "willingness_to_pay":
                if section:
                    lines.append("    willingness to pay: " + ", ".join(f"{rung} {n}" for rung, n in section.items()))
                continue
            top = section["top"]
            lines.append(f"    {name.replace('_', ' ')}: " + (f"{top['theme']} ({top['organisations']} organisations)" if top else
                         f"{section['organisations']} organisation(s); no theme stated by "
                         f"{EVIDENCE_POLICY['theme_min_organisations']}+ organisations"))
    verdict = comparison["verdict"]
    lines.append(f"  VERDICT {verdict['state']}: {verdict.get('statement') or verdict.get('reason')}")
    lines += [f"  confound: {c['detail']}" for c in comparison["confounds"]]
    lines.append(f"  not recorded, so never compared: {', '.join(comparison['not_recorded_dimensions'])}")
    return "\n".join(lines)


def render_decision(title: str, decision: dict) -> str:
    lines = [f"RECOMMENDED {title.upper()}  [RECOMMENDATION — requires human approval]", f"  {decision['recommended']}", "WHY"]
    if decision["recommended"] in UNRESOLVED:
        lines.append(f"  {decision['reason']}")
        if early := decision.get("best_early_signal"):
            lines += ["BEST EARLY SIGNAL", f"  {early['value']} [{early['state']}] — {early['qualified_replies']} qualified "
                      f"conversations, {early['meetings']} meetings, {early['proposals']} proposals, {early['customers']} customers"]
    else:
        perf = decision["commercial_performance"]
        lines += [f"  {decision['why']}", "COMMERCIAL PERFORMANCE",
                  "  " + " · ".join(f"{k.replace('_', ' ')} {_show(k, v)}" for k, v in perf.items())]
        truth = decision["buyer_truth"] or {}
        lines.append("BUYER TRUTH")
        tops = [f"  {name.replace('_', ' ')}: {section['top']['theme']} ({section['top']['organisations']} organisations)"
                for name, section in truth.items() if name != "willingness_to_pay" and section["top"]]
        lines += tops or ["  no theme stated by enough organisations"]
    lines += ["EVIDENCE STRENGTH", f"  {decision['evidence_strength']}", "MAIN UNCERTAINTY", f"  {decision['main_uncertainty']}"]
    lines += [f"CONFOUND  {c['detail']}" for c in decision.get("confounds", [])]
    return "\n".join(lines)
