"""Why performance changed: the observed change, what else changed, and what could explain it.

    OBSERVED CHANGE -> CO-OCCURRING CHANGES -> POSSIBLE EXPLANATIONS -> CAUSAL EVIDENCE -> NEXT TEST

Computed on read from funnel events, the segment unit model and buyer truth. Every label is
diagnostic. Only a controlled comparison — arms of one experiment whose declared single variable
is the only recorded difference — earns an attribution, and then only within that experiment.
"""
from __future__ import annotations

import math
from collections import Counter
from datetime import date, timedelta

from . import registries
from .buyer_truth import SEGMENT_MIN_ORGANISATIONS, _themes, buyer_evidence
from .revenue_loop import compute_metrics
from .segments import DELIVERED, EVIDENCE_POLICY, UNKNOWN, _attributes, _rate, _segment, _units, load_registry
from .storage import connect

# Every threshold a diagnosis depends on, in one place.
CHANGE_POLICY = {
    "response_window_days": EVIDENCE_POLICY["response_window_days"],
    "min_rate_denominator": EVIDENCE_POLICY["rate_min_denominator"],
    "z_threshold": 1.96,           # two-proportion test for rates
    "min_relative_change": 0.25,   # counts, money and cost metrics
    "min_count_change": 2,
    "mix_shift_share": 0.20,       # total variation distance between two windows' composition
    "status_window_days": 7,       # the status page's declared windows, printed with every result
}
INPUT_GROUPS = {
    "CREATIVE": ("creative", "hook", "body", "cta"),
    "OFFER": ("offer", "price"),
    "ROUTE": ("channel", "recipient_route"),
    "AUDIENCE": ("audience_type",),
    "MIX": ("icp", "buyer_role"),
    "EXPERIMENT": ("experiment",),
}
TRACKED = tuple(d for dims in INPUT_GROUPS.values() for d in dims) + ("campaign",)
GROUP_OF = {d: group for group, dims in INPUT_GROUPS.items() for d in dims}
GROUP_LABELS = {"CREATIVE": "POSSIBLE_CREATIVE_EFFECT", "OFFER": "POSSIBLE_OFFER_EFFECT",
                "ROUTE": "POSSIBLE_ROUTE_EFFECT", "AUDIENCE": "POSSIBLE_AUDIENCE_EFFECT", "MIX": "MIX_SHIFT",
                "EXPERIMENT": "MULTIPLE_CONFOUNDS"}
GROUP_WORDS = {"CREATIVE": "Creative", "OFFER": "Offer", "ROUTE": "Route", "AUDIENCE": "Audience",
               "MIX": "Buyer mix", "EXPERIMENT": "Experiment"}
HOLD_WORDS = {"MIX": "ICP", "AUDIENCE": "audience", "OFFER": "offer", "ROUTE": "channel and route", "CREATIVE": "message"}
# On equal materiality, the ambiguity nearer access is resolved first.
GROUP_PRIORITY = ("ROUTE", "MIX", "AUDIENCE", "OFFER", "CREATIVE", "EXPERIMENT")
VARIABLE_GROUP = {"hook": "CREATIVE", "body": "CREATIVE", "cta": "CREATIVE", "creative": "CREATIVE",
                  "subject": "CREATIVE", "format": "CREATIVE", "landing_page_headline": "CREATIVE",
                  "offer": "OFFER", "price": "OFFER", "channel": "ROUTE", "recipient_route": "ROUTE",
                  "audience": "AUDIENCE"}
# Deepest commercial meaning first; within a level, the rate before the count.
LEVELS = (
    ("revenue", ("observed_revenue_pence", "average_payment_pence", "roas", "cac")),
    ("customers", ("close_rate", "customers")),
    ("proposals", ("proposal_rate", "proposals", "pipeline_pence")),
    ("meetings", ("meeting_rate", "meetings")),
    ("qualified", ("qualified_reply_rate", "qualified_replies", "qualified_cpl")),
    ("replies", ("reply_rate", "replies", "cpl")),
    ("access", ("delivery_rate", "acceptance_rate")),
    ("attention", ("ctr", "cpc", "cpm")),
)
KIND = {
    **{m: "proportion" for m in ("close_rate", "proposal_rate", "meeting_rate", "qualified_reply_rate", "reply_rate",
                                 "acceptance_rate", "delivery_rate", "ctr")},
    **{m: "count" for m in ("customers", "proposals", "meetings", "qualified_replies", "replies")},
    "observed_revenue_pence": "money", "pipeline_pence": "money",
    **{m: "ratio" for m in ("average_payment_pence", "cpm", "cpc", "cpl", "qualified_cpl", "cac", "roas")},
}
LOWER_IS_BETTER = frozenset({"cpm", "cpc", "cpl", "qualified_cpl", "cac"})
PENCE = frozenset({"observed_revenue_pence", "pipeline_pence", "average_payment_pence", "cpm", "cpc", "cpl",
                   "qualified_cpl", "cac"})
ATTENTION_AND_COST = frozenset({"impression", "click", "landing_page_view", "lead_created", "lead_qualified",
                                "spend_recorded"})
REVENUE_DRIVERS = ("customers", "average_payment_pence", "close_rate", "proposals", "qualified_reply_rate",
                   "delivery_rate")
TRUTH_CATEGORIES = ("PROBLEM_STATED", "OBJECTION", "BUYING_CRITERION", "REASON_FOR_REJECTION")
QUIET = ("INSUFFICIENT_DATA", "NO_MEASURABLE_CHANGE")
ACTIONABLE = frozenset(set(GROUP_LABELS.values()) | {"MULTIPLE_CONFOUNDS"})
NONE = {"value": None, "numerator": 0, "denominator": 0, "basis": 0}


class ChangeError(ValueError):
    pass


def _validate(spec: dict, label: str) -> dict:
    try:
        start, end = date.fromisoformat(str(spec.get("start"))), date.fromisoformat(str(spec.get("end")))
    except ValueError as exc:
        raise ChangeError(f"{label} window needs ISO start and end dates") from exc
    if start > end:
        raise ChangeError(f"{label} window starts after it ends")
    return {**spec, "start": start.isoformat(), "end": end.isoformat()}


def _resolve(label: str, spec: dict, events: list[dict], exposures: dict, by_unit: dict, registry: dict,
             creatives: dict, evidence: list[dict], as_of: str) -> dict:
    spec = _validate(spec, label)
    start, end = spec["start"], spec["end"]
    experiment, campaign, arm = (spec.get("experiment_id") or "", spec.get("campaign_id") or "", spec.get("arm") or "")
    segment = spec.get("segment")
    units = {}
    for unit, first in exposures.items():
        attrs = _attributes(first, registry)
        if (start <= first["occurred_at"][:10] <= end and (not experiment or attrs["experiment"] == experiment)
                and (not campaign or attrs["campaign"] == campaign) and (not arm or first["arm"] == arm)
                and (not segment or attrs.get(segment[0]) == segment[1])):
            units[unit] = (first, attrs)
    delivered = {u for u in units if any(e["event_type"] in DELIVERED for e in by_unit[u])}
    first_delivery = {u: min(e["occurred_at"][:10] for e in by_unit[u] if e["event_type"] in DELIVERED) for u in delivered}
    window_days = CHANGE_POLICY["response_window_days"]
    cutoff = (date.fromisoformat(as_of[:10]) - timedelta(days=window_days)).isoformat()
    matured = {u for u, at in first_delivery.items() if at <= cutoff}
    maturity = ("NO_EXPOSURE" if not delivered else "MATURE" if len(matured) == len(delivered)
                else "IMMATURE" if not matured else "PARTIALLY_MATURE")
    matures_on = sorted((date.fromisoformat(at) + timedelta(days=window_days)).isoformat() for at in first_delivery.values())
    # ponytail: one response window for every stage; meetings, proposals and payments can take longer.
    cohort = (_segment("window", matured, by_unit, {u: attrs for u, (_, attrs) in units.items()}, evidence, cutoff,
                       "buyer_role", events, registry) if matured else None)
    dated = [e for e in events if e["event_type"] in ATTENTION_AND_COST and start <= e["occurred_at"][:10] <= end
             and (not experiment or e["experiment_id"] == experiment) and (not campaign or e["campaign_id"] == campaign)
             and (not arm or e["arm"] == arm)]
    outcomes = [e for u in matured for e in by_unit[u] if e["event_type"] not in ATTENTION_AND_COST]
    composition = _composition([(first, attrs, 1) for u, (first, attrs) in units.items() if u in delivered]
                               or [(e, _attributes(e, registry), e["quantity"]) for e in dated
                                   if e["event_type"] in ("impression", "click")], creatives)
    spend = [e["value_pence"] for e in dated if e["event_type"] == "spend_recorded"]
    return {
        "label": label, "start": start, "end": end,
        "filters": {k: v for k, v in {"experiment_id": experiment, "campaign_id": campaign, "arm": arm,
                                      "segment": "=".join(segment) if segment else ""}.items() if v},
        "maturity": maturity, "exposures": len(units), "delivered": len(delivered), "matured": len(matured),
        "matures_between": [matures_on[0], matures_on[-1]] if matures_on else [],
        "experiments": sorted({attrs["experiment"] for _, attrs in units.values()} - {UNKNOWN}),
        "campaigns": sorted({attrs["campaign"] for _, attrs in units.values()} - {UNKNOWN}),
        "arms": sorted({first["arm"] for first, _ in units.values() if first["arm"]}),
        "buyers": {u[0] for u in units}, "has_attention": bool(dated),
        "spend_pence": sum(spend) if spend else None,
        "delivery_rate": _rate(len(delivered), len(units)),
        "cohort": cohort, "metrics": compute_metrics(dated + outcomes)["metrics"], "composition": composition,
    }


def _composition(sources: list[tuple], creatives: dict) -> dict[str, dict[str, float]]:
    counts = {d: Counter() for d in TRACKED}
    for event, attrs, weight in sources:
        creative = creatives.get(event["creative_id"]) or {}
        values = {d: attrs.get(d, UNKNOWN) for d in TRACKED}
        values.update(creative=event["creative_id"] or UNKNOWN, hook=creative.get("hook") or UNKNOWN,
                      body=creative.get("body") or UNKNOWN, cta=creative.get("cta") or UNKNOWN)
        for d in TRACKED:
            counts[d][values[d]] += weight
    return {d: {value: n / total for value, n in c.items()} for d, c in counts.items() if (total := sum(c.values()))}


def _values(window: dict) -> dict[str, dict]:
    cohort, metrics = window["cohort"], window["metrics"]
    counts, rates = (cohort["counts"], cohort["rates"]) if cohort else ({}, {})
    out: dict[str, dict] = {}
    for name in ("close_rate", "proposal_rate", "meeting_rate", "qualified_reply_rate", "reply_rate", "acceptance_rate"):
        out[name] = rates.get(name) or NONE
    out["delivery_rate"] = window["delivery_rate"]
    for name in ("customers", "proposals", "meetings", "qualified_replies", "replies"):
        out[name] = {"value": counts[name], "basis": counts[name]} if counts else NONE
    out["observed_revenue_pence"] = {"value": counts["observed_revenue_pence"], "basis": counts["payments"]} if counts else NONE
    out["pipeline_pence"] = {"value": counts["pipeline_pence"], "basis": counts["proposals"]} if counts else NONE
    out["average_payment_pence"] = ({"value": counts["observed_revenue_pence"] / counts["payments"],
                                     "denominator": counts["payments"]} if counts.get("payments") else NONE)
    for name in ("ctr", "cpm", "cpc", "cpl", "qualified_cpl", "cac", "roas"):
        metric = metrics[name]
        out[name] = {"value": metric["value"], "numerator": metric.get("numerator") or 0,
                     "denominator": metric.get("denominator") or 0}
    return out


def _delta(metric: str, level: str, a: dict, b: dict) -> dict:
    kind = KIND[metric]
    delta = {"metric": metric, "level": level, "kind": kind, "baseline": a["value"], "comparison": b["value"],
             "absolute": None, "relative": None, "direction": None, "status": "NOT_DERIVABLE", "meaningful": False}
    if a["value"] is None or b["value"] is None:
        return delta
    absolute = b["value"] - a["value"]
    better = -absolute if metric in LOWER_IS_BETTER else absolute
    delta.update(absolute=absolute, relative=None if a["value"] == 0 else absolute / abs(a["value"]),
                 direction="unchanged" if absolute == 0 else "improved" if better > 0 else "deteriorated",
                 status="MEASURED")
    policy = CHANGE_POLICY
    if kind == "proportion":
        n1, n2 = a["denominator"], b["denominator"]
        if min(n1, n2) < policy["min_rate_denominator"]:
            delta["status"] = "INSUFFICIENT_DATA"
            return delta
        pooled = (a["numerator"] + b["numerator"]) / (n1 + n2)
        se = math.sqrt(pooled * (1 - pooled) * (1 / n1 + 1 / n2))
        delta["z"] = round(absolute / se, 2) if se else 0.0
        delta["meaningful"] = abs(delta["z"]) >= policy["z_threshold"]
    elif kind in ("count", "money"):
        delta["meaningful"] = (abs(b["basis"] - a["basis"]) >= policy["min_count_change"]
                               and (delta["relative"] is None or abs(delta["relative"]) >= policy["min_relative_change"]))
    else:
        enough = min(a["denominator"], b["denominator"]) >= policy["min_count_change"]
        delta["status"] = "MEASURED" if enough else "INSUFFICIENT_DATA"
        delta["meaningful"] = (enough and delta["relative"] is not None
                               and abs(delta["relative"]) >= policy["min_relative_change"])
    return delta


def _input_changes(a: dict, b: dict) -> dict[str, dict]:
    changes = {}
    for d in TRACKED:
        sa, sb = a["composition"].get(d), b["composition"].get(d)
        if sa is None or sb is None:
            changes[d] = {"baseline": sa or {}, "comparison": sb or {}, "shift": 0.0, "recorded": False, "changed": False}
            continue
        recorded = not (set(sa) == {UNKNOWN} and set(sb) == {UNKNOWN})
        shift = round(0.5 * sum(abs(sa.get(v, 0) - sb.get(v, 0)) for v in set(sa) | set(sb)), 4)
        changes[d] = {"baseline": sa, "comparison": sb, "shift": shift, "recorded": recorded,
                      "changed": recorded and shift >= CHANGE_POLICY["mix_shift_share"]}
    return changes


def _volume_changes(a: dict, b: dict) -> list[dict]:
    found = []
    for name, x, y in (("exposure_volume", a["delivered"], b["delivered"]), ("spend_pence", a["spend_pence"], b["spend_pence"])):
        if x is None or y is None:
            continue
        relative = None if x == 0 else (y - x) / x
        if abs(y - x) >= CHANGE_POLICY["min_count_change"] and (relative is None or abs(relative) >= CHANGE_POLICY["min_relative_change"]):
            found.append({"input": name, "baseline": x, "comparison": y, "relative": relative})
    return found


def _controlled(db_path: str, a: dict, b: dict, changes: dict) -> dict | None:
    experiments = set(a["experiments"]) | set(b["experiments"])
    if len(experiments) != 1 or not a["arms"] or not b["arms"] or a["arms"] == b["arms"]:
        return None
    [experiment] = experiments
    with connect(db_path) as con:
        row = con.execute("SELECT variable FROM experiments WHERE experiment_id = ?", (experiment,)).fetchone()
    variable = row["variable"] if row else ""
    changed = {d for d, c in changes.items() if c["changed"] and d != "campaign"}
    allowed = {variable} | ({"creative"} if VARIABLE_GROUP.get(variable) == "CREATIVE" else set())
    concurrent = a["start"] <= b["end"] and b["start"] <= a["end"]
    if not variable or not changed or not changed <= allowed or not concurrent:
        return None
    return {"experiment_id": experiment, "variable": variable}


def _truth_change(evidence: list[dict], a: dict, b: dict) -> dict:
    found = {}
    for category in TRUTH_CATEGORIES:
        sides = []
        for window in (a, b):
            items = [i for i in evidence if i["category"] == category and i["buyer"] in window["buyers"]]
            sides.append({theme: len({i["buyer"] for i in group}) for theme, group in _themes(items, frozenset({category})).items()})
        if sides[0] or sides[1]:
            new = set(sides[1]) - set(sides[0])
            found[category] = {"baseline": sides[0], "comparison": sides[1], "changed": set(sides[0]) != set(sides[1]),
                               "generalisable": bool(new) and all(sides[1][t] >= SEGMENT_MIN_ORGANISATIONS for t in new)}
    return found


def _label(metric: str) -> str:
    return metric.removesuffix("_pence").replace("_", " ")


def _fmt(metric: str, value) -> str:
    if value is None:
        return "NOT_DERIVABLE"
    if KIND[metric] == "proportion":
        return f"{value:.1%}"
    if metric in PENCE:
        return f"£{value / 100:,.2f}"
    return f"{value:.2f}x" if metric == "roas" else f"{value:g}"


def describe_delta(d: dict) -> str:
    text = f"{_label(d['metric'])}: {_fmt(d['metric'], d['baseline'])} → {_fmt(d['metric'], d['comparison'])}"
    if d["absolute"] is None:
        return f"{text} ({d['status']})"
    if d["kind"] == "proportion":
        absolute = f"{d['absolute'] * 100:+.1f} percentage points"
    elif d["metric"] in PENCE:
        absolute = f"{'+' if d['absolute'] >= 0 else '-'}£{abs(d['absolute']) / 100:,.2f}"
    else:
        absolute = f"{d['absolute']:+g}"
    relative = "relative change not derivable from a zero baseline" if d["relative"] is None else f"{d['relative']:+.0%}"
    flags = [d["status"]] if d["status"] != "MEASURED" else []
    flags += (["meaningful"] if d["meaningful"] else []) + ([f"z={d['z']}"] if "z" in d else [])
    return f"{text} ({absolute}, {relative}{', ' + ', '.join(flags) if flags else ''})"


def _shares(shares: dict) -> str:
    return ", ".join(f"{value} {share:.0%}" for value, share in sorted(shares.items(), key=lambda kv: (-kv[1], kv[0])))


def _next_test(label: str, groups: dict[str, float], changes: dict) -> dict:
    if label in QUIET or label == "CONTROLLED_EFFECT":
        return {"variable": None, "statement": {"INSUFFICIENT_DATA": "None yet: let the outcomes mature first.",
                                                "NO_MEASURABLE_CHANGE": "None: nothing changed that needs explaining.",
                                                "CONTROLLED_EFFECT": "None needed: the experiment already isolates its "
                                                                     "variable; run it to its declared sample."}[label]}
    candidates = {g: s for g, s in groups.items() if g != "EXPERIMENT"}
    if not candidates:
        reason = ("the windows belong to different experiments; rerun the question concurrently inside one experiment"
                  if groups else "no recorded input changed; record creative, route and ICP on every exposure before testing")
        return {"variable": None, "statement": f"None: {reason}."}
    group = max(candidates, key=lambda g: (candidates[g], -GROUP_PRIORITY.index(g)))
    changed = [d for d in INPUT_GROUPS[group] if changes[d]["changed"]]
    if group == "CREATIVE":
        elements = [d for d in ("hook", "body", "cta") if d in changed]
        variable, dimension = (elements[0], elements[0]) if len(elements) == 1 else ("creative", "creative")
    elif group == "ROUTE":
        variable = dimension = "recipient_route" if "recipient_route" in changed else "channel"
    elif group == "OFFER":
        variable = dimension = "price" if changed == ["price"] else "offer"
    else:
        variable, dimension = "audience", changed[0]
    hold = [HOLD_WORDS[g] for g in GROUP_PRIORITY if g in HOLD_WORDS and g != group
            and not (group in ("MIX", "AUDIENCE") and g in ("MIX", "AUDIENCE"))]
    return {"variable": variable, "group": group, "hold_constant": hold,
            "baseline_values": changes[dimension]["baseline"], "comparison_values": changes[dimension]["comparison"],
            "statement": f"Hold {', '.join(hold)} constant. Vary {variable} only."}


def diagnose_change(db_path: str, baseline: dict, comparison: dict, *, as_of: str | None = None) -> dict:
    """Compare two explicit windows. A window is {start, end} plus optional experiment_id, campaign_id,
    arm and segment=(dimension, value). Windows are never chosen here."""
    from .marketing_engineer import linked_events

    as_of = as_of or date.today().isoformat()
    events = linked_events(db_path)
    registry = load_registry(db_path)
    creatives = {row["creative_id"]: row for row in registries.rows(db_path, "creatives")}
    evidence = buyer_evidence(db_path)
    exposures, by_unit, _ = _units(events)
    a = _resolve("baseline", baseline, events, exposures, by_unit, registry, creatives, evidence, as_of)
    b = _resolve("comparison", comparison, events, exposures, by_unit, registry, creatives, evidence, as_of)
    va, vb = _values(a), _values(b)
    deltas = [_delta(metric, level, va[metric], vb[metric]) for level, metrics in LEVELS for metric in metrics]
    changes = _input_changes(a, b)
    groups: dict[str, float] = {}
    for d, change in changes.items():
        if change["changed"] and d in GROUP_OF:
            groups[GROUP_OF[d]] = max(groups.get(GROUP_OF[d], 0.0), change["shift"])

    comparable = all(w["delivered"] or w["has_attention"] for w in (a, b))
    if not comparable:
        state = "NOT_COMPARABLE"
    elif len(groups) >= 3:
        state = "HEAVILY_CONFOUNDED"
    elif len(groups) == 2 or "MIX" in groups or "EXPERIMENT" in groups:
        state = "PARTIALLY_CONFOUNDED"
    else:
        state = "CLEAN_COMPARISON"
    meaningful = [d for d in deltas if d["meaningful"]]
    lead = meaningful[0] if meaningful else None
    controlled = _controlled(db_path, a, b, changes)
    immature = [w["label"] for w in (a, b) if w["maturity"] == "IMMATURE"]
    if not comparable:
        label = "INSUFFICIENT_DATA"
        reason = "; ".join(f"the {w['label']} window has no delivered exposure or attention data" for w in (a, b)
                           if not (w["delivered"] or w["has_attention"]))
    elif immature:
        label = "INSUFFICIENT_DATA"
        reason = "; ".join(f"the {w['label']} window is IMMATURE: {w['delivered']} delivered, none past the "
                           f"{CHANGE_POLICY['response_window_days']}-day response window (they mature "
                           f"{w['matures_between'][0]}..{w['matures_between'][1]})" for w in (a, b) if w["label"] in immature)
    elif lead is None and not any(d["status"] == "MEASURED" and d["kind"] in ("proportion", "ratio") for d in deltas):
        # A 0 -> 0 count is not a measured non-change: without a rate that has enough observations
        # in both windows, "nothing moved" cannot be told apart from "too little to see".
        label = "INSUFFICIENT_DATA"
        reason = (f"no rate has {CHANGE_POLICY['min_rate_denominator']}+ observations in both windows "
                  f"(baseline {a['delivered']} delivered, comparison {b['delivered']} delivered)")
    elif lead is None:
        label, reason = "NO_MEASURABLE_CHANGE", "no metric moved beyond the thresholds in CHANGE_POLICY"
    elif controlled:
        label, reason = "CONTROLLED_EFFECT", ""
    elif len(groups) >= 3 or "EXPERIMENT" in groups:
        label, reason = "MULTIPLE_CONFOUNDS", ""
    elif "MIX" in groups:
        label, reason = "MIX_SHIFT", ""
    elif len(groups) == 2:
        label, reason = "MULTIPLE_CONFOUNDS", ""
    elif groups:
        label, reason = GROUP_LABELS[next(iter(groups))], ""
    else:
        label, reason = ("IMPROVED" if lead["direction"] == "improved" else "DETERIORATED"), ""

    truth = _truth_change(evidence, a, b)
    changed_dims = [d for d, c in changes.items() if c["changed"]]
    diagnosis = {
        "as_of": as_of[:10], "classification": label, "reason": reason, "comparison_state": state,
        "baseline": {k: v for k, v in a.items() if k not in ("cohort", "metrics", "composition", "buyers")},
        "comparison": {k: v for k, v in b.items() if k not in ("cohort", "metrics", "composition", "buyers")},
        "deltas": deltas, "lead_change": lead,
        "observed_change": describe_delta(lead) if lead else None,
        "what_changed": [{"input": d, "group": GROUP_OF.get(d, "CAMPAIGN"), "baseline": changes[d]["baseline"],
                          "comparison": changes[d]["comparison"], "shift": changes[d]["shift"]} for d in changed_dims]
                        + _volume_changes(a, b),
        "what_stayed_constant": [d for d, c in changes.items() if c["recorded"] and not c["changed"]],
        "not_recorded": [d for d, c in changes.items() if not c["recorded"]],
        "confounds": [f"{GROUP_WORDS[g].lower()} changed: {', '.join(d for d in INPUT_GROUPS[g] if changes[d]['changed'])}"
                      for g in GROUP_PRIORITY if g in groups]
                     + [f"the {w['label']} window is PARTIALLY_MATURE: {w['matured']} of {w['delivered']} exposures "
                        "have matured; only those are in the denominators" for w in (a, b) if w["maturity"] == "PARTIALLY_MATURE"],
        "controlled_by": controlled, "buyer_truth_change": truth,
    }
    diagnosis["supported_interpretation"] = _interpretation(diagnosis, groups, changes, deltas)
    diagnosis["unsupported_claims"] = _unsupported(diagnosis, groups, changes)
    diagnosis["next_test"] = _next_test(label, groups, changes)
    return diagnosis


def _interpretation(diagnosis: dict, groups: dict, changes: dict, deltas: list[dict]) -> str:
    label, lead = diagnosis["classification"], diagnosis["lead_change"]
    if label in QUIET:
        return diagnosis["reason"][:1].upper() + diagnosis["reason"][1:] + "."
    metric = _label(lead["metric"])
    if label == "CONTROLLED_EFFECT":
        c = diagnosis["controlled_by"]
        text = (f"Within {c['experiment_id']}, whose declared single variable is {c['variable']}, the {metric} difference "
                f"between arms is attributable to {c['variable']}, within the limits of that experiment.")
    elif label in GROUP_LABELS.values() and label != "MIX_SHIFT" and len(groups) == 1:
        text = (f"{GROUP_WORDS[next(iter(groups))]} change is a plausible explanation for the {metric} change; "
                "no other recorded input changed.")
    elif label == "MIX_SHIFT":
        shifted = [f"{d} ({_shares(changes[d]['baseline'])} → {_shares(changes[d]['comparison'])})"
                   for g in ("MIX", "AUDIENCE", "ROUTE") for d in INPUT_GROUPS[g] if changes[d]["changed"]]
        text = (f"The {metric} change coincided with a material mix shift in {'; '.join(shifted)}; the aggregate may "
                "reflect who was reached rather than what was sent.")
    elif label == "MULTIPLE_CONFOUNDS":
        text = (f"The {metric} change coincided with changes in {', '.join(GROUP_WORDS[g].lower() for g in GROUP_PRIORITY if g in groups)}; "
                "the recorded data cannot separate them.")
    else:
        text = f"{metric[:1].upper() + metric[1:]} {lead['direction']} with no recorded input change: the recorded data holds no candidate explanation."
    if lead["level"] in ("revenue", "customers"):
        by_metric = {d["metric"]: d for d in deltas}
        drivers = [f"{describe_delta(by_metric[m])}" for m in REVENUE_DRIVERS
                   if by_metric[m]["absolute"] not in (None, 0)]
        upstream = [_label(d["metric"]) for d in deltas if d["meaningful"] and d["level"] in ("access", "attention")
                    and d["direction"] != lead["direction"]]
        if drivers:
            text += " Near the revenue transition: " + "; ".join(drivers) + "."
        if upstream:
            text += f" {', '.join(upstream)} moved the other way and did not carry through to revenue."
    return text


def _unsupported(diagnosis: dict, groups: dict, changes: dict) -> list[str]:
    label, lead = diagnosis["classification"], diagnosis["lead_change"]
    claims = []
    if lead and label != "CONTROLLED_EFFECT":
        metric = _label(lead["metric"])
        claims += [f"The {d} change ({_shares(changes[d]['baseline'])} → {_shares(changes[d]['comparison'])}) caused the "
                   f"{metric} change." for g in GROUP_PRIORITY if g in groups for d in INPUT_GROUPS[g] if changes[d]["changed"]]
        if not groups:
            claims.append(f"Any named cause of the {metric} change.")
    if label == "CONTROLLED_EFFECT":
        c = diagnosis["controlled_by"]
        claims.append(f"{c['variable']} has the same effect outside {c['experiment_id']} or on other buyers.")
    for category, change in diagnosis["buyer_truth_change"].items():
        if change["changed"] and not change["generalisable"]:
            claims.append(f"The market changed: the observed {category.lower().replace('_', ' ')} mix changed, but not "
                          f"across {SEGMENT_MIN_ORGANISATIONS}+ independent organisations per new theme.")
    return claims


def default_windows(as_of: str) -> tuple[dict, dict]:
    """The status page's declared windows: the two most recent whole windows whose exposures have
    all passed the response window. Printed with every result; never presented as causal."""
    days = CHANGE_POLICY["status_window_days"]
    end = date.fromisoformat(as_of[:10]) - timedelta(days=CHANGE_POLICY["response_window_days"])
    comparison = {"start": (end - timedelta(days=days - 1)).isoformat(), "end": end.isoformat()}
    baseline_end = end - timedelta(days=days)
    baseline = {"start": (baseline_end - timedelta(days=days - 1)).isoformat(), "end": baseline_end.isoformat()}
    return baseline, comparison


def change_summary(db_path: str, *, as_of: str, events: list[dict]) -> dict | None:
    if not any(e["event_type"] in DELIVERED for e in events):
        return None
    baseline, comparison = default_windows(as_of)
    return diagnose_change(db_path, baseline, comparison, as_of=as_of)


def diagnosis_proposal(diagnosis: dict | None, history: list[dict]) -> dict | None:
    """One variable that would resolve the most material ambiguity a diagnosis found."""
    if not diagnosis or diagnosis["classification"] not in ACTIONABLE or not diagnosis["next_test"]["variable"]:
        return None
    test, lead = diagnosis["next_test"], diagnosis["lead_change"]
    return {
        "status": "PROPOSED_NEEDS_CONTRACT", "experiment_id": None, "based_on_experiment_id": None,
        "hypothesis": f"Holding {', '.join(test['hold_constant'])} constant, changing only {test['variable']} moves "
                      f"{_label(lead['metric'])}.",
        "single_variable": test["variable"],
        "control": f"{test['variable']} as recorded in the baseline window: {_shares(test['baseline_values'])}",
        "variant": f"{test['variable']} as recorded in the comparison window: {_shares(test['comparison_values'])}",
        "icp": "carried over", "offer": "carried over", "channel": "carried over", "primary_metric": lead["metric"],
        "guardrails": ["declare before exposure (experiment_trust_guardrails)"],
        "sample_and_stopping_rule": f"concurrent arms, each reaching {CHANGE_POLICY['min_rate_denominator']} matured "
                                    "exposures: two time windows are not two arms",
        "why_highest_value": f"{diagnosis['classification']}: {diagnosis['supported_interpretation']}",
        "evidence": [diagnosis["observed_change"]], "previous_experiments": history,
        "stop_condition": f"If {_label(lead['metric'])} does not differ between concurrent arms, {test['variable']} did not "
                          "drive the observed change: return to the next co-occurring change.",
    }


def render_change(d: dict) -> str:
    lines = ["PERFORMANCE CHANGE  [OBSERVED deltas · DERIVED co-occurring changes · not causal unless CONTROLLED_EFFECT]"]
    for key in ("baseline", "comparison"):
        w = d[key]
        lines.append(f"{key.upper():<11} {w['start']} → {w['end']} · {w['maturity']} · exposures {w['exposures']}, "
                     f"delivered {w['delivered']}, matured {w['matured']}"
                     + (f" (mature {w['matures_between'][0]}..{w['matures_between'][1]})" if w["matures_between"] else "")
                     + (f" · {', '.join(w['experiments'])}" if w["experiments"] else "")
                     + (" · " + ", ".join(f"{k}={v}" for k, v in w["filters"].items()) if w["filters"] else ""))
    lines += [f"COMPARISON STATE  {d['comparison_state']}", f"DIAGNOSIS  {d['classification']}"]

    def section(title: str, body: list[str]) -> None:
        if body:
            lines.extend(["", title] + [f"  {line}" for line in body])

    section("OBSERVED CHANGE", [d["observed_change"]] if d["observed_change"] else [d["reason"]])
    section("OTHER MEASURED DELTAS", [describe_delta(x) for x in d["deltas"]
                                      if x["absolute"] is not None and x is not d["lead_change"]
                                      and not (x["baseline"] == 0 and x["comparison"] == 0)])
    section("WHAT ALSO CHANGED", [f"{c['input']}: {_shares(c['baseline'])} → {_shares(c['comparison'])} (shift {c['shift']:.0%})"
                                  if "shift" in c else f"{c['input']}: {c['baseline']} → {c['comparison']}"
                                  for c in d["what_changed"]])
    section("WHAT STAYED CONSTANT", [", ".join(d["what_stayed_constant"])] if d["what_stayed_constant"] else [])
    section("NOT RECORDED", [", ".join(d["not_recorded"])] if d["not_recorded"] else [])
    section("CONFOUNDS", d["confounds"])
    section("SUPPORTED INTERPRETATION", [d["supported_interpretation"]])
    section("UNSUPPORTED CLAIMS", d["unsupported_claims"])
    section("BUYER TRUTH CHANGE", [f"{cat.lower()}: {c['baseline']} → {c['comparison']}"
                                   for cat, c in d["buyer_truth_change"].items() if c["changed"]])
    section("NEXT TEST", [d["next_test"]["statement"]])
    return "\n".join(lines)
