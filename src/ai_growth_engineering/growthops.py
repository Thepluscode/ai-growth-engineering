"""Bounded GrowthOps operator for internal commercial decision support.

It reads operational state and proposes one next move. The surrounding workbench may
persist human-approved workflow state, but it cannot send, spend or publish externally.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from . import registries
from .economics import funnel_rates, revenue_per_customer
from .product_opportunities import ProductBuildGate, opportunity_from_registry
from .registry import reply_rate_by_route, scoreboard
from .storage import connect


TARGETS = {
    "qualified_prospects": 100,
    "outreach_sent": 100,
    "meaningful_responses": 20,
    "discovery_calls": 10,
    "diagnostics_proposed": 5,
    "commercial_proposals": 3,
    "paying_customers": 1,
    "collected_revenue_pence": 500_000,
}

METRIC_LABELS = {
    "qualified_prospects": "Qualified prospects",
    "outreach_sent": "Delivered outreach",
    "meaningful_responses": "Meaningful replies",
    "discovery_calls": "Discovery calls",
    "diagnostics_proposed": "Diagnostics proposed",
    "commercial_proposals": "Proposals",
    "paying_customers": "Paying customers",
    "collected_revenue_pence": "Collected revenue",
}


def command_center_state(db_path: str, *, today: date | None = None) -> dict[str, Any]:
    """Assemble the operating state consumed by the Command Center."""
    today = today or date.today()
    metrics = scoreboard(db_path)
    last_contact = _last_contact_date(db_path)
    days_since_contact = (today - last_contact).days if last_contact else None
    constraint, recommendation = _next_move(metrics)

    return {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "mode": "INTERNAL / HUMAN GATED / NO AUTOSEND",
        "status": {
            "level": constraint[0],
            "label": constraint[1],
            "reason": constraint[2],
        },
        "recommendation": recommendation,
        "freshness": {
            "last_external_contact": last_contact.isoformat() if last_contact else None,
            "days_since_external_contact": days_since_contact,
        },
        "scoreboard": [
            {
                "key": key,
                "label": METRIC_LABELS[key],
                "value": value,
                "target": TARGETS[key],
                "ratio": min(value / TARGETS[key], 1) if TARGETS[key] else 0,
                "kind": "money" if key.endswith("_pence") else "count",
            }
            for key, value in metrics.items()
        ],
        "funnel": funnel_rates(metrics),
        "revenue_per_customer_pence": revenue_per_customer(metrics),
        "routes": _routes(db_path),
        "experiments": _experiments(db_path),
        "evidence": _evidence(db_path),
        "opportunities": _opportunities(db_path),
        "channels": _channels(db_path),
        "authority": {
            "mode": "HUMAN_GATED",
            "allowed": [
                "read operational data",
                "identify the highest-priority constraint",
                "rank evidence-backed options",
                "rank eligible intent prospects with source provenance",
                "create sourced teardown and outbound drafts",
                "record an operator-confirmed send or reply",
            ],
            "human_approval_required": [
                "contact a customer or prospect",
                "publish externally",
                "spend or change a budget",
                "change an experiment contract",
            ],
        },
    }


def _next_move(metrics: dict[str, int]) -> tuple[tuple[str, str, str], dict[str, Any]]:
    """The highest-priority constraint, read from what the funnel has actually done.

    There used to be a time-since-last-contact freeze ahead of everything here. It was
    the first branch, so it shadowed every other diagnosis, and with no sends going out
    it was permanently red — which makes it wallpaper rather than a rule, and hid the
    real constraint underneath it for as long as it stayed lit.
    """
    if metrics["outreach_sent"] == 0:
        return (
            ("red", "NO MARKET CONTACT", "The system has no delivered outreach."),
            _recommendation(
                "Create the first external observation",
                "Send one qualified message manually; do not automate an unobserved route.",
                "delivered_outreach",
                "Human approval is required before sending.",
            ),
        )
    if metrics["meaningful_responses"] == 0:
        return (
            ("red", "ACCESS CONSTRAINT", "Delivered outreach has produced no meaningful reply."),
            _recommendation(
                "Change access before increasing volume",
                "Test one reachable buyer route with a fixed message and keep channel and recipient class separate.",
                "meaningful_reply_rate_by_route",
                "Human approval is required for contact and spend.",
            ),
        )
    if metrics["discovery_calls"] == 0:
        return (
            ("amber", "DISCOVERY CONSTRAINT", "Replies exist but none became discovery."),
            _recommendation(
                "Convert a reply into discovery",
                "Ask for a bounded conversation and capture the buyer's last ten wanted opportunities.",
                "discovery_calls",
                "Human approval is required before replying.",
            ),
        )
    if metrics["commercial_proposals"] == 0:
        return (
            ("amber", "COMMERCIAL CONSTRAINT", "Discovery exists without a proposal."),
            _recommendation(
                "Sell the smallest paid next step",
                "Use observed economics to propose a diagnostic or a bounded delivery sprint.",
                "commercial_proposals",
                "Human approval is required before a proposal leaves the company.",
            ),
        )
    if metrics["paying_customers"] == 0:
        return (
            ("amber", "DECISION CONSTRAINT", "A proposal exists without payment."),
            _recommendation(
                "Resolve the buying decision",
                "Record the budget owner, objection, decision date, and smallest acceptable commitment.",
                "paying_customers",
                "Human approval is required for commercial terms.",
            ),
        )
    return (
        ("green", "DELIVERY LEARNING", "At least one paying customer is recorded."),
        _recommendation(
            "Turn delivery into evidence",
            "Measure usage, outcome, margin, and the repeated workflow before automating it.",
            "customer_outcome_and_margin",
            "Human approval remains required for external actions.",
        ),
    )


def _recommendation(title: str, action: str, metric: str, approval: str) -> dict[str, Any]:
    return {
        "title": title,
        "action": action,
        "primary_metric": metric,
        "approval": approval,
        "executable": False,
    }


def _last_contact_date(db_path: str) -> date | None:
    with connect(db_path) as con:
        value = con.execute(
            """SELECT MAX(substr(sent_at, 1, 10)) FROM outreach
               WHERE sent_at IS NOT NULL AND stage != 'bounced'"""
        ).fetchone()[0]
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _routes(db_path: str) -> list[dict[str, Any]]:
    output = []
    for route, values in sorted(reply_rate_by_route(db_path).items()):
        sent = values["sent"]
        output.append({
            "route": route,
            **values,
            "reply_rate": values["replies"] / sent if sent else None,
        })
    return output


def _experiments(db_path: str) -> list[dict[str, Any]]:
    with connect(db_path) as con:
        rows = con.execute(
            """SELECT experiment_id, hypothesis, primary_metric, minimum_sample,
                      sample_size, observed_value, decision, channel
               FROM experiments ORDER BY created_at DESC, experiment_id"""
        ).fetchall()
    return [
        {
            **dict(row),
            "progress": min(row["sample_size"] / row["minimum_sample"], 1)
            if row["minimum_sample"] else 0,
        }
        for row in rows
    ]


def _evidence(db_path: str, limit: int = 8) -> list[dict[str, Any]]:
    with connect(db_path) as con:
        rows = con.execute(
            """SELECT evidence_id, kind, statement, source, confidence, observed, created_at
               FROM evidence ORDER BY created_at DESC, rowid DESC LIMIT ?""",
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def _opportunities(db_path: str) -> list[dict[str, Any]]:
    output = []
    for row in registries.rows(db_path, "product_opportunities"):
        try:
            opportunity = opportunity_from_registry(row)
        except (TypeError, ValueError) as exc:
            output.append({
                "opportunity_id": row["product_opportunity_id"],
                "buyer": row["buyer"],
                "problem": row["problem"],
                "status": "invalid",
                "eligible": False,
                "missing": ["registry_contract_error"],
                "decision": str(exc),
            })
            continue
        decision = ProductBuildGate.evaluate(opportunity)
        output.append({
            "opportunity_id": opportunity.opportunity_id,
            "buyer": opportunity.buyer,
            "problem": opportunity.problem,
            "status": opportunity.status.value,
            "eligible": decision.eligible,
            "missing": list(decision.missing),
            "decision": opportunity.decision,
        })
    return output


def _channels(db_path: str) -> list[dict[str, Any]]:
    return [
        {
            "channel_id": row["channel_id"],
            "name": row["name"],
            "kind": row["kind"],
            "status": row["status"],
            "notes": row["notes"],
        }
        for row in registries.rows(db_path, "channels")
    ]
