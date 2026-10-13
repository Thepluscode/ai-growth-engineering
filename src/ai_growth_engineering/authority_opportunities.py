"""Evidence-gated authority opportunities built from existing marketing registries.

This is not a content generator. It decides whether an evidence-backed authority asset has
enough commercial context and distribution access to merit a publishing test, then exposes
the lineage from market evidence to revenue. Publishing remains human-gated.
"""
from __future__ import annotations

from dataclasses import dataclass

from . import registries
from .storage import connect, init_db


TOPIC_CLASSES = frozenset({
    "pain", "mistake", "contrarian", "evidence", "mechanism", "decision",
    "economics", "teardown", "prediction_with_conditions", "tool",
})
ASSET_TIERS = frozenset({
    "proprietary_authority_asset", "analytical_content", "distribution_content",
})
SCORE_FIELDS = (
    "commercial_buyer_value", "problem_urgency", "existing_spend_signal",
    "information_demand", "answer_quality_gap", "evidence_availability",
    "right_to_win", "distribution_access", "product_adjacency",
)


def _ids(value: object) -> tuple[str, ...]:
    return tuple(dict.fromkeys(part.strip() for part in str(value or "").split(";") if part.strip()))


@dataclass(frozen=True)
class AuthorityOpportunity:
    opportunity_id: str
    market_id: str
    buyer: str
    problem: str
    information_gap: str
    authority_supply: str
    topic: str
    topic_class: str
    thesis: str
    proposed_asset: str
    conversion_event: str
    market_evidence_ids: tuple[str, ...] = ()
    proof_evidence_ids: tuple[str, ...] = ()
    claim_ids: tuple[str, ...] = ()
    channel_ids: tuple[str, ...] = ()
    offer_id: str = ""
    content_id: str = ""
    asset_tier: str = ""
    commercial_buyer_value: int = 0
    problem_urgency: int = 0
    existing_spend_signal: int = 0
    information_demand: int = 0
    answer_quality_gap: int = 0
    evidence_availability: int = 0
    right_to_win: int = 0
    distribution_access: int = 0
    product_adjacency: int = 0
    status: str = "research"
    notes: str = ""

    def __post_init__(self) -> None:
        if not self.opportunity_id.strip():
            raise ValueError("opportunity_id is required")
        if self.topic_class not in TOPIC_CLASSES:
            raise ValueError(f"topic_class must be one of {sorted(TOPIC_CLASSES)}")
        if self.asset_tier and self.asset_tier not in ASSET_TIERS:
            raise ValueError(f"asset_tier must be one of {sorted(ASSET_TIERS)}")
        for name in SCORE_FIELDS:
            if not 0 <= getattr(self, name) <= 5:
                raise ValueError(f"{name} must be between 0 and 5")


def from_registry(row: dict) -> AuthorityOpportunity:
    return AuthorityOpportunity(
        opportunity_id=row["authority_opportunity_id"],
        market_id=row["market_id"], buyer=row["buyer"], problem=row["problem"],
        information_gap=row["information_gap"], authority_supply=row["authority_supply"],
        topic=row["topic"], topic_class=row["topic_class"], thesis=row["thesis"],
        proposed_asset=row["proposed_asset"], conversion_event=row["conversion_event"],
        market_evidence_ids=_ids(row.get("market_evidence_ids")),
        proof_evidence_ids=_ids(row.get("proof_evidence_ids")),
        claim_ids=_ids(row.get("claim_ids")), channel_ids=_ids(row.get("channel_ids")),
        offer_id=row.get("offer_id", ""), content_id=row.get("content_id", ""),
        asset_tier=row.get("asset_tier", ""),
        **{name: int(row.get(name, 0) or 0) for name in SCORE_FIELDS},
        status=row.get("status", "research"), notes=row.get("notes", ""),
    )


def _reference_sets(db_path: str) -> dict[str, dict[str, dict]]:
    with connect(db_path) as con:
        evidence = {row["evidence_id"]: dict(row) for row in con.execute("SELECT * FROM evidence")}
    return {
        "evidence": evidence,
        "markets": {row["market_id"]: row for row in registries.rows(db_path, "markets")},
        "claims": {row["claim_id"]: row for row in registries.rows(db_path, "claims")},
        "channels": {row["channel_id"]: row for row in registries.rows(db_path, "channels")},
        "offers": {row["offer_id"]: row for row in registries.rows(db_path, "offers")},
    }


def _missing(opportunity: AuthorityOpportunity, refs: dict[str, dict[str, dict]], db_path: str) -> list[str]:
    missing: list[str] = []
    for name in ("market_id", "buyer", "problem", "information_gap", "authority_supply",
                 "topic", "thesis", "proposed_asset", "conversion_event", "content_id",
                 "asset_tier"):
        if not str(getattr(opportunity, name)).strip():
            missing.append(name)
    for name, values in (("market_evidence", opportunity.market_evidence_ids),
                         ("proof_evidence", opportunity.proof_evidence_ids),
                         ("claim", opportunity.claim_ids), ("channel", opportunity.channel_ids)):
        if not values:
            missing.append(name)
    for name in SCORE_FIELDS:
        if getattr(opportunity, name) == 0:
            missing.append(name)
    if opportunity.market_id not in refs["markets"]:
        missing.append(f"unknown_market:{opportunity.market_id}")
    if not opportunity.offer_id:
        missing.append("offer_id")
    elif opportunity.offer_id not in refs["offers"]:
        missing.append(f"unknown_offer:{opportunity.offer_id}")
    for name, values, registry in (
        ("evidence", opportunity.market_evidence_ids + opportunity.proof_evidence_ids, "evidence"),
        ("claim", opportunity.claim_ids, "claims"), ("channel", opportunity.channel_ids, "channels"),
    ):
        missing.extend(f"unknown_{name}:{value}" for value in values if value not in refs[registry])
    for evidence_id in opportunity.market_evidence_ids:
        evidence = refs["evidence"].get(evidence_id)
        if evidence and not evidence["observed"]:
            missing.append(f"market_evidence_not_observed:{evidence_id}")
    for evidence_id in opportunity.proof_evidence_ids:
        evidence = refs["evidence"].get(evidence_id)
        if evidence and not evidence["observed"]:
            missing.append(f"proof_evidence_not_observed:{evidence_id}")
    linked_evidence = set(opportunity.market_evidence_ids + opportunity.proof_evidence_ids)
    from .registry import claim_publication_check

    for claim_id in opportunity.claim_ids:
        claim = refs["claims"].get(claim_id)
        if claim and claim["evidence_id"] not in linked_evidence:
            missing.append(f"claim_evidence_not_linked:{claim_id}")
        if claim and not claim_publication_check(db_path, claim_id).allowed:
            missing.append(f"claim_not_publishable:{claim_id}")
    if opportunity.status == "parked":
        missing.append("parked")
    return list(dict.fromkeys(missing))


def _outcomes(db_path: str, content_id: str) -> dict:
    funnels = [row for row in registries.rows(db_path, "conversation_funnels")
               if row["content_id"] == content_id]
    attributions = [row for row in registries.rows(db_path, "attribution")
                    if row["content_id"] == content_id]
    return {
        "funnels": len(funnels),
        "approved": any(row.get("distribution_status") in {"approved", "published", "observation_complete"} for row in funnels),
        "published": any(bool(row.get("published_at")) for row in funnels),
        "measured": any(bool(row.get("measured_at")) for row in funnels),
        "content_views": sum(row["content_views"] for row in funnels),
        "qualified_leads": sum(row["qualified_leads"] for row in funnels),
        "dm_starts": sum(row["dm_starts"] for row in funnels),
        "opportunities": sum(row["opportunities"] for row in funnels),
        "attributions": len(attributions),
        "revenue_pence": sum(row["revenue_pence"] for row in attributions),
    }


def _graph(opportunity: AuthorityOpportunity, refs: dict[str, dict[str, dict]], outcomes: dict) -> list[dict]:
    def values(ids: tuple[str, ...], registry: str, label: str) -> list[dict]:
        return [{"id": value, "label": refs[registry].get(value, {}).get(label, "UNKNOWN")}
                for value in ids]

    def observed_state(count: int) -> str:
        if count:
            return "observed"
        return "observed_zero" if outcomes["measured"] else "not_observed"

    distribution_state = "observed" if outcomes["published"] or outcomes["content_views"] else (
        "approved" if outcomes["approved"] else ("available" if opportunity.channel_ids else "unknown")
    )
    return [
        {"stage": "market_evidence", "state": "observed" if opportunity.market_evidence_ids else "unknown", "items": values(opportunity.market_evidence_ids, "evidence", "statement")},
        {"stage": "topic", "state": "inferred", "items": [{"id": opportunity.topic_class, "label": opportunity.topic}]},
        {"stage": "thesis", "state": "inferred", "items": values(opportunity.claim_ids, "claims", "statement")},
        {"stage": "proof", "state": "observed" if opportunity.proof_evidence_ids else "unknown", "items": values(opportunity.proof_evidence_ids, "evidence", "statement")},
        {"stage": "authority_asset", "state": "registered", "items": [{"id": opportunity.content_id, "label": opportunity.proposed_asset, "tier": opportunity.asset_tier}]},
        {"stage": "distribution", "state": distribution_state, "items": values(opportunity.channel_ids, "channels", "name")},
        {"stage": "discovery", "state": observed_state(outcomes["content_views"]), "items": [{"content_views": outcomes["content_views"]}]},
        {"stage": "qualified_audience", "state": observed_state(outcomes["qualified_leads"]), "items": [{"qualified_leads": outcomes["qualified_leads"]}]},
        {"stage": "conversation", "state": observed_state(outcomes["dm_starts"]), "items": [{"dm_starts": outcomes["dm_starts"], "target_event": opportunity.conversion_event}]},
        {"stage": "offer", "state": "registered", "items": values((opportunity.offer_id,), "offers", "outcome")},
        {"stage": "opportunity", "state": observed_state(outcomes["opportunities"]), "items": [{"opportunities": outcomes["opportunities"]}]},
        {"stage": "revenue", "state": "observed" if outcomes["attributions"] else "not_observed", "items": [{"attributions": outcomes["attributions"], "revenue_pence": outcomes["revenue_pence"]}]},
    ]


def readout(db_path: str) -> dict:
    init_db(db_path)
    refs = _reference_sets(db_path)
    rows = []
    for stored in registries.rows(db_path, "authority_opportunities"):
        opportunity = from_registry(stored)
        missing = _missing(opportunity, refs, db_path)
        outcomes = _outcomes(db_path, opportunity.content_id)
        priority = None if missing else sum(getattr(opportunity, name) for name in SCORE_FIELDS)
        if missing and any(name in missing for name in ("market_evidence", "information_demand", "existing_spend_signal")):
            action = "Test the existing asset through one approved channel and record qualified discovery before creating more content."
        elif missing:
            action = "Resolve the named evidence or lineage gaps before proposing distribution."
        else:
            action = "Ready for founder review of one bounded distribution test; publishing remains approval-required."
        rows.append({
            "authority_opportunity_id": opportunity.opportunity_id,
            "market_id": opportunity.market_id, "buyer": opportunity.buyer,
            "problem": opportunity.problem, "information_gap": opportunity.information_gap,
            "authority_supply": opportunity.authority_supply,
            "topic": opportunity.topic, "topic_class": opportunity.topic_class,
            "thesis": opportunity.thesis, "proposed_asset": opportunity.proposed_asset,
            "content_id": opportunity.content_id, "asset_tier": opportunity.asset_tier,
            "status": "READY" if not missing else "RESEARCH",
            "priority": priority, "missing": missing, "recommended_action": action,
            "authority": "R3_APPROVAL_REQUIRED", "scores": {name: getattr(opportunity, name) for name in SCORE_FIELDS},
            "graph": _graph(opportunity, refs, outcomes),
        })
    rows.sort(key=lambda row: (row["priority"] is None, -(row["priority"] or 0), row["authority_opportunity_id"]))
    return {"opportunities": rows, "ready": sum(row["status"] == "READY" for row in rows),
            "research": sum(row["status"] == "RESEARCH" for row in rows),
            "authority": "R3_APPROVAL_REQUIRED"}
