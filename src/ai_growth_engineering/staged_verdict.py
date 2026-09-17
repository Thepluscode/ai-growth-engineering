"""Staged verdict: an experiment's own preregistered ACCESS and DEMAND gates, applied to canonical data.

Every threshold comes from the experiment's preregistered-gates file, transcribed from its
preregistration with citations. Nothing here holds a number of its own.

Two questions never merge. ACCESS asks whether buyers could be reached and routed; DEMAND asks
whether reached buyers wanted it. A routing reply answers the first and never the second.

Silence is read only when three things hold: the preregistered window has closed, a governed reply
check ran after it, and no reply waits in review. Even then silence says the tested configuration
drew no response. It never says the problem, the ICP or the willingness to pay is absent.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from .buyer_truth import buyer_evidence
from .funnel_events import effective_events, recipient_class
from .revenue_loop import entity, undelivered_units
from .storage import connect, init_db

REQUIRED = ("experiment_id", "judge_not_before", "demand_exposure_counted", "access", "demand",
            "research_snapshot", "response_mapping", "next_actions")
REPLY_EVENTS = frozenset({"reply_received", "reply_meaningful"})
MEETING_EVENTS = frozenset({"meeting_booked", "meeting_held"})
CUSTOMER_EVENTS = frozenset({"customer_won", "payment_received"})
NOT_ESTABLISHED = (
    "that the underlying problem is absent",
    "that the market does not need the product",
    "that the ICP is invalid",
    "that buyers will not pay",
)
# The failure point decides the next uncertainty; the experiment's own file decides the action.
FAILURE_POINTS = (
    ("customers", "the offer converted at least once: expand only what paid"),
    ("proposals_without_customers", "price / objection / trust / buying criteria"),
    ("meetings_without_proposals", "offer / commercial value"),
    ("demand_without_meetings", "CTA / commitment level / offer"),
    ("routing_without_demand", "correct buyer / positioning / problem framing"),
    ("no_human_replies", "access / message / route"),
)


class VerdictError(ValueError):
    pass


def load_rules(path: str | Path) -> dict:
    rules = json.loads(Path(path).read_text(encoding="utf-8"))
    missing = [key for key in REQUIRED if key not in rules]
    if missing:
        raise VerdictError(f"{path} lacks preregistered rules {missing}; a verdict never fills a gap with a default")
    return rules


def _responses(db_path: str, experiment_id: str, rules: dict) -> dict:
    scoped = [e for e in effective_events(db_path) if e["experiment_id"] == experiment_id]
    mapping = rules["response_mapping"]
    categories: dict[str, set[str]] = defaultdict(set)
    evidence = [i for i in buyer_evidence(db_path) if i["experiment_id"] == experiment_id]
    for item in evidence:
        categories[item["buyer"]].add(item["category"])
    replied = {entity(e) for e in scoped if e["event_type"] in REPLY_EVENTS}
    meetings = {entity(e) for e in scoped if e["event_type"] in MEETING_EVENTS}
    # The protocol's own "pain conversation": a meeting booked, or a proposal requested.
    qualified = meetings | {b for b, cats in categories.items() if "PROPOSAL_REQUESTED" in cats}
    demand = {b for b in replied if categories[b] & set(mapping["demand"])}
    routing = {b for b in replied if categories[b] & set(mapping["routing"])}
    classes = {}
    for buyer in sorted(replied | qualified):
        classes[buyer] = ("QUALIFIED_CONVERSATION" if buyer in qualified else "DEMAND_SIGNAL" if buyer in demand
                          else "ROUTING_ONLY" if buyer in routing else "GENERAL_REPLY")
    themes: dict[str, set[str]] = defaultdict(set)
    ids: dict[str, set[str]] = defaultdict(set)
    for item in evidence:
        if item["interpretation"]:
            themes[item["interpretation"]["theme"]].add(item["buyer"])
            ids[item["interpretation"]["theme"]].add(item["evidence_id"])
    return {
        "classes": classes, "route_confirmed": routing,
        "counts": {cls: sum(1 for c in classes.values() if c == cls)
                   for cls in ("GENERAL_REPLY", "ROUTING_ONLY", "DEMAND_SIGNAL", "QUALIFIED_CONVERSATION")},
        "human_replies": len(replied), "meetings": len(meetings),
        "proposals_sent": len({entity(e) for e in scoped if e["event_type"] == "proposal_sent"}),
        "customers": len({entity(e) for e in scoped if e["event_type"] in CUSTOMER_EVENTS}),
        "revenue_pence": (sum(e["value_pence"] for e in scoped if e["event_type"] == "payment_received")
                          - sum(e["value_pence"] for e in scoped if e["event_type"] == "refund")),
        "buyer_truth": [{"theme": t, "organisations": len(b), "evidence_ids": sorted(ids[t])}
                        for t, b in sorted(themes.items(), key=lambda kv: (-len(kv[1]), kv[0]))],
    }


def _review_state(db_path: str, experiment_id: str) -> tuple[int, int, str | None]:
    from .reply_capture import review

    with connect(db_path) as con:
        threads = {r["thread_id"] for r in con.execute("SELECT thread_id FROM outbound_messages WHERE experiment_id = ?",
                                                       (experiment_id,))}
        recipients = {r["recipient"] for r in con.execute("SELECT recipient FROM outbound_messages WHERE experiment_id = ?",
                                                          (experiment_id,))}
        automated = con.execute(
            f"SELECT COUNT(*) FROM reply_candidates WHERE kind IN ('AUTOMATED', 'OUT_OF_OFFICE') AND "
            f"source_thread_id IN ({','.join('?' * len(threads)) or 'NULL'})", tuple(threads)).fetchone()[0]
        last_check = con.execute("SELECT MAX(checked_at) FROM reply_checks WHERE experiment_id = ?",
                                 (experiment_id,)).fetchone()[0]
    pending = sum(1 for c in review(db_path)["pending"] if c["source_thread_id"] in threads or c["sender"] in recipients)
    return pending, automated, last_check


def _access(rules: dict, route_confirmed: set[str], sends: int, resolved: bool) -> tuple[str, list[str]]:
    gate, snap = rules["access"], rules["research_snapshot"]
    if snap["desk_eligible"] < gate["min_desk_eligible"]:
        return "RESEARCH_SHORTFALL", [f"{snap['desk_eligible']} desk-eligible of {gate['min_desk_eligible']}"]
    verified = {c.lower() for c in snap["direct_access_companies"]} | route_confirmed
    short = []
    if snap["named_buyers"] < gate["min_named_buyers"]:
        short.append(f"named buyers {snap['named_buyers']} < {gate['min_named_buyers']}")
    if len(verified) < gate["min_verified_access_accounts"]:
        short.append(f"verified-access accounts {len(verified)} < {gate['min_verified_access_accounts']} "
                     f"({len(snap['direct_access_companies'])} DIRECT from research, {len(route_confirmed)} route-confirmed by reply)")
    notes = [f"clean-delivery rate not judged: it is measured on demand exposures, and this stage has "
             f"{'none' if not rules['demand_exposure_counted'] else 'too few'} (minimum {gate['min_observed_for_rate']} observed)"]
    if not short:
        return "PASS", ["buyers named and verified access reached"] + notes
    if sends == 0:
        return "DESK_ACCESS_SHORTFALL", short + ["no routing attempt has been made"] + notes
    if not resolved:
        return "ROUTING_IN_PROGRESS", short + ["routing attempts are not yet resolved"] + notes
    return "FAILED", short + notes


def _demand(rules: dict, clean: int, r: dict) -> tuple[str, list[str]]:
    gate = rules["demand"]
    if r["customers"] >= gate["min_paid_partners"]:
        return "PASS", [f"{r['customers']} paid design partner(s)"]
    if clean < gate["min_clean_deliveries"]:
        reason = (f"{clean} clean deliveries to named buyers of {gate['min_clean_deliveries']} required"
                  + ("" if rules["demand_exposure_counted"] else ": this stage's sends are access attempts, not demand exposures"))
        return "NOT_ASKED", [reason]
    failures = [f"{label} {have} < {need}" for label, have, need in (
        ("replies", r["human_replies"], gate["min_replies"]),
        ("pain conversations", r["counts"]["QUALIFIED_CONVERSATION"], gate["min_pain_conversations"]),
        ("proposals", r["proposals_sent"], gate["min_proposals"])) if have < need]
    if failures:
        return "KILL", ["a full cycle completed against clean deliveries and: " + "; ".join(failures)]
    return "NOT_ASKED", ["reply, conversation and proposal gates met; no paid design partner yet"]


def verdict(db_path: str, rules: dict, *, as_of: str) -> dict:
    init_db(db_path)
    experiment = rules["experiment_id"]
    today, window = as_of[:10], rules["judge_not_before"]
    scoped = [e for e in effective_events(db_path) if e["experiment_id"] == experiment]
    undelivered = undelivered_units(scoped)
    sends = [e for e in scoped if e["event_type"] == "message_sent"]
    delivered = [e for e in sends if (entity(e), e["experiment_id"]) not in undelivered]
    r = _responses(db_path, experiment, rules)
    pending, automated, last_check = _review_state(db_path, experiment)
    mature = today >= window
    checked_after_window = bool(last_check) and last_check[:10] >= window
    resolved = mature and checked_after_window and not pending
    clean = (sum(1 for e in delivered if recipient_class(e["metadata"]) == "named_buyer")
             if rules["demand_exposure_counted"] else 0)
    access, access_reasons = _access(rules, r["route_confirmed"], len(sends), resolved)
    demand, demand_reasons = _demand(rules, clean, r)
    n = len(delivered)
    result = {
        "experiment_id": experiment, "as_of": today, "judge_not_before": window,
        "attempted_sends": len(sends), "delivery_failures": len({entity(e) for e in scoped if e["event_type"] == "message_bounced"}),
        "delivered_exposures": n, "matured_exposures": n if mature else 0, "immature_exposures": 0 if mature else n,
        "historically_claimed_sends": rules["research_snapshot"].get("sends_claimed"),
        "automated_responses": automated, "human_replies": r["human_replies"],
        "response_classes": r["counts"], "meetings": r["meetings"], "proposals_sent": r["proposals_sent"],
        "customers": r["customers"], "revenue_pence": r["revenue_pence"], "pending_reviews": pending,
        "last_reply_check": last_check, "clean_deliveries_to_named_buyers": clean,
        # Each rate says what it is, and none is a gate unless the protocol declared it. Before the
        # window closes there is no rate at all: a 0% printed on day seven reads as a result.
        "rates": {name: (None if not n or not mature else round(count / n, 4)) for name, count in (
            ("human_reply_rate", r["human_replies"]), ("routing_reply_rate", r["counts"]["ROUTING_ONLY"]),
            ("demand_signal_rate", r["counts"]["DEMAND_SIGNAL"] + r["counts"]["QUALIFIED_CONVERSATION"]),
            ("qualified_conversation_rate", r["counts"]["QUALIFIED_CONVERSATION"]))},
        "access_verdict": access, "access_reasons": access_reasons,
        "demand_verdict": demand, "demand_reasons": demand_reasons,
        "buyer_truth": r["buyer_truth"], "what_this_does_not_establish": list(NOT_ESTABLISHED),
    }
    good_news = access == "PASS" or demand == "PASS"
    if not good_news and not resolved:
        blockers = ([f"the preregistered window is open until {window}; silence before then is not a result"] if not mature else [])
        blockers += ([f"no governed reply check has run on or after {window}: run `age replies check` first"]
                     if mature and not checked_after_window else [])
        blockers += ([f"{pending} reply candidate(s) await review; approve or reject them before any verdict"] if pending else [])
        return {**result, "status": "NOT_READY", "blockers": blockers, "final_maturity_date": window}

    demand_seen = r["counts"]["DEMAND_SIGNAL"] + r["counts"]["QUALIFIED_CONVERSATION"]
    if good_news:
        status = "POSITIVE"
    elif access == "FAILED" or demand == "KILL":
        status = "MIXED" if (r["route_confirmed"] or demand_seen) else "NEGATIVE"
    else:
        status = "INCONCLUSIVE"

    if r["customers"]:
        point = "customers"
    elif r["proposals_sent"]:
        point = "proposals_without_customers"
    elif r["meetings"]:
        point = "meetings_without_proposals"
    elif demand_seen:
        point = "demand_without_meetings"
    elif r["human_replies"]:
        point = "routing_without_demand"
    else:
        point = "no_human_replies"
    if not r["human_replies"]:
        interpretation = f"The tested outreach configuration produced no observed buyer response in {n} delivered exposures."
    elif not demand_seen:
        interpretation = "Access produced routing information but no observed demand evidence."
    else:
        interpretation = (f"{demand_seen} buyer(s) gave demand evidence"
                          + ("" if rules["demand_exposure_counted"] else
                             ", recorded as non-preregistered for this stage: it informs, and it counts toward no gate")
                          + ".")
    return {**result, "status": status, "failure_point": point,
            "uncertainty": dict(FAILURE_POINTS)[point],
            "commercial_interpretation": interpretation,
            "next_decision": rules["next_actions"].get(point, "not declared in the preregistration: a person decides")}


def render_verdict(v: dict) -> str:
    def money(p):
        return "none observed" if not p else f"£{p / 100:,.2f}"

    lines = [f"{v['experiment_id']} VERDICT  [preregistered gates applied to canonical data]", "", "STATUS", f"  {v['status']}"]
    if v["status"] == "NOT_READY":
        lines += ["", "BLOCKERS"] + [f"  {b}" for b in v["blockers"]]
    counts = v["response_classes"]
    lines += ["", "EXPOSURE",
              f"  attempted sends {v['attempted_sends']} · delivery failures {v['delivery_failures']} · delivered {v['delivered_exposures']}"
              f" (matured {v['matured_exposures']}, immature {v['immature_exposures']}; judged from {v['judge_not_before']})"]
    if v.get("historically_claimed_sends") is not None and v["historically_claimed_sends"] != v["attempted_sends"]:
        lines.append(f"  historical claim {v['historically_claimed_sends']} sends; the canonical verified count is used")
    lines += ["", "RESPONSES",
              f"  automated (never buyer replies) {v['automated_responses']} · human replies {v['human_replies']} · "
              f"routing only {counts['ROUTING_ONLY']} · general {counts['GENERAL_REPLY']} · demand signals {counts['DEMAND_SIGNAL']} · "
              f"qualified conversations {counts['QUALIFIED_CONVERSATION']}",
              f"  meetings {v['meetings']} · proposals {v['proposals_sent']} · design partners {v['customers']} · "
              f"observed revenue {money(v['revenue_pence'])} · pending reviews {v['pending_reviews']}",
              "  rates: " + " · ".join(f"{k} {'n/a' if x is None else f'{x:.1%}'}" for k, x in v["rates"].items()),
              "", "PREREGISTERED GATES",
              f"  ACCESS {v['access_verdict']}: " + "; ".join(v["access_reasons"]),
              f"  DEMAND {v['demand_verdict']}: " + "; ".join(v["demand_reasons"])]
    if v["buyer_truth"]:
        lines += ["", "APPROVED BUYER EVIDENCE"] + [
            f"  {t['theme']}: {t['organisations']} organisation(s) · {', '.join(t['evidence_ids'])}" for t in v["buyer_truth"]]
    if v["status"] != "NOT_READY":
        lines += ["", "COMMERCIAL INTERPRETATION", f"  {v['commercial_interpretation']}",
                  "", "WHAT THIS DOES NOT ESTABLISH"] + [f"  {x}" for x in v["what_this_does_not_establish"]] + [
                  "", "NEXT DECISION", f"  failure point: {v['failure_point']} · uncertainty: {v['uncertainty']}",
                  f"  {v['next_decision']}"]
    return "\n".join(lines)
