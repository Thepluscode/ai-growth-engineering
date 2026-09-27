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
from .funnel_events import effective_events

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
    links = [l for l in registries.rows(db_path, "market_experiments") if l["layer"] == "DEMAND"]
    market_rows = {m["market_id"]: m for m in registries.rows(db_path, "markets")}
    active = sorted({l["market_id"] for l in links})

    rows = []
    for market_id in active:
        mine = [l for l in links if l["market_id"] == market_id]
        demand = markets.layer_evidence(db_path, market_id)["DEMAND"]["protocols"]
        sent = sum(p["exposures"] for p in demand.values())
        replies = sum(p["positives"] for p in demand.values())
        this_week = sum(
            int(e.get("quantity") or 1) for e in events for l in mine
            if e["experiment_id"] == l["experiment_id"] and e["event_type"] == l["exposure_event"]
            and start <= str(e["occurred_at"])[:10] <= end)
        remaining = max(0, min_exposures - sent)
        rows.append({
            "market_id": market_id, "buyer": market_rows.get(market_id, {}).get("buyer", ""),
            "experiments": sorted({l["experiment_id"] for l in mine}),
            "sent": sent, "replies": replies, "sent_this_week": this_week,
            "reply_rate": round(replies / sent, 4) if sent >= min_exposures else None,
            "status": "MEASURABLE" if remaining == 0 else f"NEEDS_{remaining}_MORE",
            "this_week_to_do": max(0, min(weekly_target, remaining) - this_week) if remaining else 0,
        })

    comparisons = [markets.compare(db_path, a, b, "DEMAND", min_exposures)
                   for a, b in combinations(active, 2)]
    return {"as_of": as_of.isoformat(), "week": [start, end], "weekly_target": weekly_target,
            "min_exposures": min_exposures, "markets": rows,
            "comparisons": [{"markets": c["markets"], "verdict": c["verdict"], "reason": c["reason"]}
                            for c in comparisons]}


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
        lines.append(f"  sent {m['sent']} · replies {m['replies']} · reply rate {rate} · {m['status']}")
        lines.append(f"  this week: sent {m['sent_this_week']}"
                     + (f" · TO DO: research and draft {m['this_week_to_do']} more named buyers"
                        if m["this_week_to_do"] else ""))
        lines.append("")
    lines.append("COMPARISONS (DEMAND)")
    for c in data["comparisons"]:
        lines.append(f"  {' vs '.join(c['markets'])}: {c['verdict']}"
                     + (f" — {c['reason']}" if c["reason"] else ""))
    lines.append("")
    lines.append("Nothing is sent by this system. Draft in the Command Center, approve, send by hand, "
                 "record the send and any reply there.")
    return "\n".join(lines)
