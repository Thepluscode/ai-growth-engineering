"""The weekly marketing readout: one page answering what to do this week, per product market.

The loop it closes: the operator researches named buyers → drafts in the workbench tagged with
the market's experiment → approves and sends by hand → records replies → this readout says how
far each market is from a measurable sample and what the comparison between markets allows.

It counts only what the market layer counts (effective events of linked experiments; the
workbench refuses role inboxes for them), so the readout and the comparison cannot disagree.
It never recommends dropping a market below its minimum sample: zero replies from twelve
messages is not a rejection.
"""
from __future__ import annotations

from datetime import date, timedelta
from itertools import combinations

from . import markets, registries
from .demand_funnel import report as demand_report
from .funnel_events import effective_events
from .outbound_workbench import DIRECT_VERIFIED, PROFILE_VERIFIED, workbench_state

DEFAULT_WEEKLY_TARGET = 15          # named buyers per market per week; 30 in two weeks


def _week(as_of: date) -> tuple[str, str]:
    return (as_of - timedelta(days=6)).isoformat(), as_of.isoformat()


def readout(db_path: str, as_of: date | None = None, weekly_target: int = DEFAULT_WEEKLY_TARGET,
            min_exposures: int = markets.DEFAULT_MIN_EXPOSURES) -> dict:
    as_of = as_of or date.today()
    weekly_target = max(1, int(weekly_target))
    min_exposures = max(1, int(min_exposures))
    start, end = _week(as_of)
    events = effective_events(db_path)
    funnel_rows = {row["market_id"]: row for row in demand_report(
        db_path, min_delivered=min_exposures)["markets"]}
    drafts = workbench_state(db_path)["drafts"]
    links = [l for l in registries.rows(db_path, "market_experiments") if l["layer"] == "DEMAND"]
    market_rows = {m["market_id"]: m for m in registries.rows(db_path, "markets")}
    # A parked market keeps its history but is not this week's work.
    active = sorted({l["market_id"] for l in links
                     if market_rows.get(l["market_id"], {}).get("status", "") in ("", "active")})

    rows = []
    for market_id in active:
        mine = [l for l in links if l["market_id"] == market_id]
        experiment_ids = {l["experiment_id"] for l in mine}
        funnel = funnel_rows[market_id]
        sent = funnel["messages_attempted"]
        delivered = funnel["delivered_to_named_buyers"]
        replies = funnel["meaningful_replies"]
        sent_this_week = sum(
            int(e.get("quantity") or 1) for e in events for l in mine
            if e["experiment_id"] == l["experiment_id"] and e["event_type"] == "message_sent"
            and start <= str(e["occurred_at"])[:10] <= end)
        active_drafts = [d for d in drafts if d["experiment_id"] in experiment_ids
                         and d["status"] in ("pending_approval", "approved")]
        queued = len(active_drafts)
        pending_approval = sum(d["status"] == "pending_approval" for d in active_drafts)
        approved = sum(d["status"] == "approved" for d in active_drafts)
        direct_ready = sum(d["route_status"] == DIRECT_VERIFIED for d in active_drafts)
        profile_ready = sum(d["route_status"] == PROFILE_VERIFIED for d in active_drafts)
        route_unverified = queued - direct_ready - profile_ready
        variants = [{key: value for key, value in variant.items()
                     if key in ("protocol", "experiments", "messages_attempted",
                                "delivered_to_named_buyers", "meaningful_replies",
                                "evidence_gate", "primary_rate")}
                    for variant in funnel["variants"]]
        sample_target = min_exposures * len(variants)
        sample_remaining = sum(max(0, min_exposures - variant["delivered_to_named_buyers"])
                               for variant in variants)
        send_remaining = (max(0, min(weekly_target, sample_remaining) - sent_this_week)
                          if sample_remaining else 0)
        research_remaining = max(0, send_remaining - queued)
        rows.append({
            "market_id": market_id, "buyer": market_rows.get(market_id, {}).get("buyer", ""),
            "experiments": sorted(experiment_ids),
            "sent": sent, "delivered": delivered, "replies": replies,
            "sent_this_week": sent_this_week, "queued": queued,
            "pending_approval": pending_approval, "approved": approved,
            "direct_ready": direct_ready, "profile_ready": profile_ready,
            "route_unverified": route_unverified,
            "delivery_evidence_pending": funnel["attempted_delivery_unverified"],
            # Multiple variants are never pooled into one market-level rate.
            "reply_rate": (variants[0]["primary_rate"] if len(variants) == 1 else None),
            "variants": variants,
            "status": "MEASURABLE" if sample_remaining == 0 else f"NEEDS_{sample_remaining}_MORE",
            "sample_target": sample_target,
            "sample_remaining": sample_remaining,
            "send_remaining": send_remaining,
            "research_remaining": research_remaining,
            # Kept for API compatibility. It means research work only, never send work.
            "this_week_to_do": research_remaining,
        })

    by_market = {row["market_id"]: row for row in rows}
    comparisons = [_compare_delivered(by_market[a], by_market[b], min_exposures)
                   for a, b in combinations(active, 2)]
    return {"as_of": as_of.isoformat(), "week": [start, end], "weekly_target": weekly_target,
            "min_exposures": min_exposures, "markets": rows,
            "comparisons": [{"markets": c["markets"], "verdict": c["verdict"], "reason": c["reason"]}
                            for c in comparisons]}


def _compare_delivered(a: dict, b: dict, minimum: int) -> dict:
    """Compare like-for-like variants using verified named-buyer deliveries only."""
    variants_a = {row["protocol"]: row for row in a["variants"]}
    variants_b = {row["protocol"]: row for row in b["variants"]}
    shared = sorted(set(variants_a) & set(variants_b))
    comparisons = []
    for protocol in shared:
        sides = []
        for market, variant in ((a["market_id"], variants_a[protocol]),
                                (b["market_id"], variants_b[protocol])):
            delivered = variant["delivered_to_named_buyers"]
            replies = variant["meaningful_replies"]
            sides.append({"market": market, "experiments": variant["experiments"],
                          "exposures": delivered, "positives": replies,
                          "rate": round(replies / delivered, 4) if delivered else None})
        short = [side["market"] for side in sides if side["exposures"] < minimum]
        comparisons.append({"protocol": protocol, "sides": sides,
                            "verdict": "NOT_ENOUGH_EVIDENCE" if short else "COMPARABLE",
                            "reason": (f"below {minimum} verified deliveries: {', '.join(short)}"
                                       if short else "")})
    comparable = [row for row in comparisons if row["verdict"] == "COMPARABLE"]
    reason = "" if comparable else (
        "every shared protocol is below the verified-delivery minimum" if shared
        else "no shared message protocol; variants are never pooled")
    return {"layer": "DEMAND", "markets": [a["market_id"], b["market_id"]],
            "min_exposures": minimum,
            "verdict": "COMPARABLE" if comparable else "NOT_ENOUGH_EVIDENCE",
            "reason": reason, "comparisons": comparisons}


def render(data: dict) -> str:
    lines = [f"WEEKLY MARKETING READOUT  {data['week'][0]} .. {data['week'][1]}",
             f"minimum sample {data['min_exposures']} named buyers per market · "
             f"weekly target {data['weekly_target']}", ""]
    if not data["markets"]:
        return "\n".join(lines + ["No market has a DEMAND experiment linked. Register one in "
                                  "seeds/registries.json (markets + market_experiments)."])
    for m in data["markets"]:
        rate = f"{m['reply_rate']:.1%}" if m["reply_rate"] is not None else "not yet measurable"
        lines.append(f"{m['market_id']}  ({', '.join(m['experiments'])})")
        lines.append(f"  buyer: {m['buyer'] or 'unspecified'}")
        lines.append(f"  attempted {m['sent']} · delivered to named buyers {m['delivered']} · "
                     f"replies {m['replies']} · reply rate {rate} · {m['status']}")
        if len(m.get("variants", [])) > 1:
            for v in m["variants"]:
                lines.append(f"    variant {v['protocol']} ({', '.join(v['experiments'])}): "
                             f"attempted {v['messages_attempted']} · verified delivery "
                             f"{v['delivered_to_named_buyers']} · replies {v['meaningful_replies']}")
        lines.append(f"  this week: attempted {m['sent_this_week']} · queued {m['queued']} · "
                     f"SEND TO DO {m['send_remaining']} · research to do {m['research_remaining']} · "
                     f"routes: {m['direct_ready']} direct / {m['profile_ready']} profile / "
                     f"{m['route_unverified']} unresolved")
        lines.append("")
    lines.append("COMPARISONS (DEMAND)")
    for c in data["comparisons"]:
        lines.append(f"  {' vs '.join(c['markets'])}: {c['verdict']}"
                     + (f" — {c['reason']}" if c["reason"] else ""))
    lines.append("")
    lines.append("Nothing is sent by this system. Draft in the Command Center, approve, send by hand, "
                 "record the send and any reply there.")
    return "\n".join(lines)
