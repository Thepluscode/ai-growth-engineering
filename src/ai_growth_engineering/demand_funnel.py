"""The demand funnel: fifteen stages per market and per message variant, from research to revenue.

The weekly readout counts sends and replies. That cannot say whether a zero is a demand answer
or an access failure, because it never separated *reaching a buyer* from *asking them*. This
report keeps every stage apart:

    research   1 companies researched  2 qualified  3 named buyers  4 valid direct routes
    access     5 attempted  6 delivered  7 delivered to named buyers
    response   8 meaningful replies  9 qualified replies  10 discovery conversations
    truth      11 pain confirmed  12 existing spend  13 solution requested
    money      14 paid commitments  15 revenue

Invariants:
- Stages 1-4 come from the evidence set (a private research file that names people, so it is
  never committed). Without it they are None - unknown, never zero.
- Stages 5-15 come from the effective event log and buyer-truth categories of the market's
  linked DEMAND experiments only. A role inbox is never a named buyer.
- The primary rate is meaningful replies / delivered to named buyers, and only at or above the
  minimum sample. All historical attempts are never the denominator.
- Variants (protocols) are reported side by side and never pooled into a rate.
- The thesis state is derived, strongest evidence first; replies alone never raise it above
  ACCESS_INCONCLUSIVE, and a routing failure never lowers it to PAIN_NOT_CONFIRMED. STOP_THESIS
  is a founder decision recorded as the market's status, never computed.
"""
from __future__ import annotations

from collections import defaultdict

from . import markets, registries
from .funnel_events import effective_events
from .revenue_loop import entity
from .storage import connect, init_db

STATES = ("ACCESS_INCONCLUSIVE", "PAIN_NOT_CONFIRMED", "PAIN_CONFIRMED", "SPEND_CONFIRMED",
          "PAID_TEST_REQUESTED", "PAID_COMMITMENT", "STOP_THESIS")
DEFAULT_MIN_CONVERSATIONS = 5       # discovery conversations before "no pain" means anything
ROUTED = ("high", "medium")         # a verified email or a verified profile link; a name alone is not
# Stage -> buyer-truth category. Existing spend has no category of its own: BUDGET_SIGNAL is the
# nearest one, and the mapping is stated here so the report never implies more than it holds.
TRUTH = {"pain_confirmations": "PAIN_CONFIRMED", "spend_confirmations": "BUDGET_SIGNAL",
         "solution_requests": "PROPOSAL_REQUESTED"}


def _research(rows: list[dict] | None) -> dict:
    if rows is None:
        return {k: None for k in ("companies_researched", "qualified_companies", "named_buyers",
                                  "valid_direct_routes")}
    qualified = [r for r in rows if all(str(r.get(k) or "").strip() for k in
                                        ("evidence_trigger", "evidence_quote", "evidence_url", "role"))]
    named = [r for r in qualified if str(r.get("person_name") or "").strip()]
    return {"companies_researched": len({str(r.get("company", "")).casefold() for r in rows}),
            "qualified_companies": len(qualified), "named_buyers": len(named),
            "valid_direct_routes": sum(str(r.get("route_confidence", "")).lower() in ROUTED for r in named)}


def _recipient_class(event: dict) -> str:
    meta = event.get("metadata") or {}
    return meta.get("recipient_class_review") or meta.get("recipient_class") or "unclassified"


def _stages(events: list[dict], truth: dict[str, set[str]], experiments: set[str]) -> dict:
    mine = [e for e in events if e["experiment_id"] in experiments]

    def who(*types: str) -> set[str]:
        return {entity(e) for e in mine if e["event_type"] in types}

    sent, bounced = who("message_sent"), who("message_bounced")
    delivered = sent - bounced
    named = {entity(e) for e in mine if e["event_type"] == "message_sent"
             and _recipient_class(e) == "named_buyer"} - bounced
    return {"messages_attempted": len(sent | bounced), "messages_delivered": len(delivered),
            "delivered_to_named_buyers": len(named),
            "meaningful_replies": len(who("reply_meaningful")),
            "qualified_replies": len(who("lead_qualified")),
            "discovery_conversations": len(who("meeting_held")),
            **{stage: len(truth[category]) for stage, category in TRUTH.items()},
            "paid_commitments": len(who("proposal_accepted", "customer_won")),
            "revenue_pence": sum(int(e.get("value_pence") or 0) for e in mine
                                 if e["event_type"] == "payment_received")}


def _truth(db_path: str, experiments: set[str]) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {c: set() for c in TRUTH.values()}
    if not experiments:
        return out
    with connect(db_path) as con:
        for row in con.execute(
                f"""SELECT category, lower(coalesce(nullif(company, ''), person_id)) AS who
                    FROM commercial_evidence WHERE experiment_id IN ({','.join('?' for _ in experiments)})""",
                sorted(experiments)):
            if row["category"] in out:
                out[row["category"]].add(row["who"])
    return out


def classify(stages: dict, status: str = "", min_conversations: int = DEFAULT_MIN_CONVERSATIONS) -> str:
    if status == "stop_thesis":
        return "STOP_THESIS"
    for stage, state in (("paid_commitments", "PAID_COMMITMENT"), ("solution_requests", "PAID_TEST_REQUESTED"),
                         ("spend_confirmations", "SPEND_CONFIRMED"), ("pain_confirmations", "PAIN_CONFIRMED")):
        if stages[stage]:
            return state
    if stages["discovery_conversations"] >= max(1, min_conversations):
        return "PAIN_NOT_CONFIRMED"
    return "ACCESS_INCONCLUSIVE"


def report(db_path: str, evidence_set: list[dict] | None = None,
           min_delivered: int = markets.DEFAULT_MIN_EXPOSURES,
           min_conversations: int = DEFAULT_MIN_CONVERSATIONS) -> dict:
    init_db(db_path)
    min_delivered = max(1, int(min_delivered))
    events = effective_events(db_path)
    market_rows = {m["market_id"]: m for m in registries.rows(db_path, "markets")}
    links = defaultdict(list)
    for link in registries.rows(db_path, "market_experiments"):
        if link["layer"] == "DEMAND":
            links[link["market_id"]].append(link)
    by_market: dict[str, list[dict]] | None = None
    if evidence_set is not None:
        by_market = defaultdict(list)
        for row in evidence_set:
            by_market[str(row.get("market_id", ""))].append(row)

    out = []
    for market_id in sorted(links):
        status = market_rows.get(market_id, {}).get("status", "")
        if status not in ("", "active", "stop_thesis"):
            continue                                    # parked: history kept, not this cycle's thesis
        experiments = {l["experiment_id"] for l in links[market_id]}
        stages = _stages(events, _truth(db_path, experiments), experiments)
        variants = []
        for protocol in sorted({l["protocol"] for l in links[market_id]}):
            exps = {l["experiment_id"] for l in links[market_id] if l["protocol"] == protocol}
            v = _stages(events, _truth(db_path, exps), exps)
            n = v["delivered_to_named_buyers"]
            variants.append({"protocol": protocol, "experiments": sorted(exps), **v,
                             "primary_rate": round(v["meaningful_replies"] / n, 4) if n >= min_delivered else None})
        out.append({"market_id": market_id, "status": status or "active",
                    **_research(None if by_market is None else by_market.get(market_id, [])),
                    **stages, "variants": variants,
                    "thesis_state": classify(stages, status, min_conversations)})
    return {"min_delivered": min_delivered, "min_conversations": min_conversations, "markets": out,
            "evidence_set_rows": None if evidence_set is None else len(evidence_set)}


STAGE_LABELS = (
    ("companies_researched", "1 companies researched"), ("qualified_companies", "2 qualified companies"),
    ("named_buyers", "3 named buyers identified"), ("valid_direct_routes", "4 valid direct routes"),
    ("messages_attempted", "5 messages attempted"), ("messages_delivered", "6 messages delivered"),
    ("delivered_to_named_buyers", "7 delivered to named buyers"), ("meaningful_replies", "8 meaningful replies"),
    ("qualified_replies", "9 qualified replies"), ("discovery_conversations", "10 discovery conversations"),
    ("pain_confirmations", "11 pain confirmations"), ("spend_confirmations", "12 existing-spend confirmations"),
    ("solution_requests", "13 solution requests"), ("paid_commitments", "14 paid commitments"),
    ("revenue_pence", "15 revenue (pence)"),
)


def render(data: dict) -> str:
    lines = [f"DEMAND FUNNEL  (primary rate = meaningful replies / delivered to named buyers, "
             f"shown at >= {data['min_delivered']})", ""]
    if data["evidence_set_rows"] is None:
        lines += ["Stages 1-4 UNKNOWN: no evidence set given (--evidence-set private/<file>.json).", ""]
    for m in data["markets"]:
        lines.append(f"{m['market_id']}  [{m['thesis_state']}]")
        for key, label in STAGE_LABELS:
            value = m[key]
            lines.append(f"  {label:<34} {'UNKNOWN' if value is None else value}")
        for v in m["variants"]:
            rate = f"{v['primary_rate']:.1%}" if v["primary_rate"] is not None else "not yet measurable"
            lines.append(f"  variant {v['protocol']} ({', '.join(v['experiments'])}): delivered-named "
                         f"{v['delivered_to_named_buyers']} · meaningful {v['meaningful_replies']} · "
                         f"conversations {v['discovery_conversations']} · rate {rate}")
        lines.append("")
    lines.append("Thesis states are derived; STOP_THESIS is only ever the founder's recorded decision.")
    return "\n".join(lines)
