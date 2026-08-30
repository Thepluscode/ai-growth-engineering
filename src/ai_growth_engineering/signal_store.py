"""Durable signal-intelligence store — NOT WIRED TO ANY SURFACE.

Kept specialised rather than forcing buyer-intelligence semantics into the generic
marketing registries. Existing databases migrate in place through idempotent CREATE TABLE.

Its tables are the ones `storage._separate_legacy_revenue_signal_table` renamed out of
the operational path, so nothing in the application writes to them and `ranked_prospects`
returns [] against any real store. The operational path is `signal_intelligence`, whose
`intelligence_state` reads `intent_signals` and `prospect_identities`.

`command_center_state` used to publish `ranked_prospects` as `intent_prospects`, which meant
the API carried a buyer list that was structurally always empty, with a test asserting the
emptiness as correct. That field is gone. Do not re-expose this module without first moving
the writers over — an always-empty surface reads as "no buyers", not as "wrong table".
"""
from __future__ import annotations

import json
from dataclasses import asdict

from .revenue_signal_intelligence import (
    IntentSignal,
    PriorityInput,
    ProspectEligibilityGate,
    ProspectEligibilityInput,
    priority_score,
)
from .storage import connect


SIGNAL_SCHEMA = """
CREATE TABLE IF NOT EXISTS revenue_intent_signals (
    signal_id TEXT PRIMARY KEY,
    prospect_id TEXT NOT NULL,
    company TEXT NOT NULL,
    signal_type TEXT NOT NULL,
    source TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    evidence_id TEXT NOT NULL,
    confidence REAL NOT NULL,
    strength INTEGER NOT NULL,
    commercial_interpretation TEXT NOT NULL DEFAULT '',
    raw_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS identity_resolutions (
    identity_id TEXT PRIMARY KEY,
    prospect_id TEXT NOT NULL,
    company TEXT NOT NULL,
    person_name TEXT NOT NULL,
    buyer_role TEXT NOT NULL,
    status TEXT NOT NULL,
    provider TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT '',
    email TEXT NOT NULL DEFAULT '',
    linkedin_url TEXT NOT NULL DEFAULT '',
    reachable_channel TEXT NOT NULL DEFAULT '',
    confidence REAL NOT NULL DEFAULT 0,
    verified_at TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS prospect_signal_lineage (
    lineage_id TEXT PRIMARY KEY,
    prospect_id TEXT NOT NULL,
    signal_id TEXT NOT NULL REFERENCES revenue_intent_signals(signal_id),
    evidence_id TEXT NOT NULL,
    identity_id TEXT NOT NULL DEFAULT '',
    offer_id TEXT NOT NULL DEFAULT '',
    angle_id TEXT NOT NULL DEFAULT '',
    experiment_id TEXT NOT NULL DEFAULT '',
    channel_id TEXT NOT NULL DEFAULT '',
    recommended_action TEXT NOT NULL DEFAULT '',
    outcome_id TEXT NOT NULL DEFAULT '',
    revenue_pence INTEGER NOT NULL DEFAULT 0,
    contribution_profit_pence INTEGER NOT NULL DEFAULT 0,
    recorded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


def init_signal_store(db_path: str) -> None:
    with connect(db_path) as con:
        con.executescript(SIGNAL_SCHEMA)


def add_signal(db_path: str, signal: IntentSignal, *, raw: dict | None = None) -> None:
    signal.validate()
    init_signal_store(db_path)
    with connect(db_path) as con:
        evidence = con.execute(
            "SELECT 1 FROM evidence WHERE evidence_id = ?", (signal.evidence_id,)
        ).fetchone()
        if evidence is None:
            raise ValueError("signal evidence_id must exist in evidence registry")
        con.execute(
            """INSERT INTO revenue_intent_signals(
                   signal_id, prospect_id, company, signal_type, source, observed_at,
                   evidence_id, confidence, strength, commercial_interpretation, raw_json
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                signal.signal_id, signal.prospect_id, signal.company, signal.signal_type,
                signal.source, signal.observed_at, signal.evidence_id, signal.confidence,
                signal.strength, signal.commercial_interpretation,
                json.dumps(raw or {}, sort_keys=True),
            ),
        )


def add_identity(
    db_path: str,
    *,
    identity_id: str,
    prospect_id: str,
    company: str,
    person_name: str,
    buyer_role: str,
    status: str,
    reachable_channel: str,
    provider: str = "",
    source: str = "",
    email: str = "",
    linkedin_url: str = "",
    confidence: float = 0.0,
    verified_at: str = "",
) -> None:
    if status not in ProspectEligibilityGate.VERIFIED_IDENTITIES | {"unverified", "ambiguous", "unreachable"}:
        raise ValueError("unknown identity status")
    if not 0 <= confidence <= 1:
        raise ValueError("confidence must be between 0 and 1")
    for name, value in {
        "identity_id": identity_id,
        "prospect_id": prospect_id,
        "company": company,
        "person_name": person_name,
        "buyer_role": buyer_role,
    }.items():
        if not value.strip():
            raise ValueError(f"{name} is required")
    init_signal_store(db_path)
    with connect(db_path) as con:
        con.execute(
            """INSERT INTO identity_resolutions(
                   identity_id, prospect_id, company, person_name, buyer_role, status,
                   provider, source, email, linkedin_url, reachable_channel, confidence, verified_at
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                identity_id, prospect_id, company, person_name, buyer_role, status,
                provider, source, email, linkedin_url, reachable_channel, confidence, verified_at,
            ),
        )


def add_lineage(
    db_path: str,
    *,
    lineage_id: str,
    prospect_id: str,
    signal_id: str,
    evidence_id: str,
    identity_id: str = "",
    offer_id: str = "",
    angle_id: str = "",
    experiment_id: str = "",
    channel_id: str = "",
    recommended_action: str = "",
    outcome_id: str = "",
    revenue_pence: int = 0,
    contribution_profit_pence: int = 0,
) -> None:
    if revenue_pence < 0:
        raise ValueError("revenue_pence cannot be negative")
    init_signal_store(db_path)
    with connect(db_path) as con:
        signal = con.execute(
            "SELECT evidence_id FROM revenue_intent_signals WHERE signal_id = ?", (signal_id,)
        ).fetchone()
        if signal is None:
            raise ValueError("signal_id must exist")
        if signal["evidence_id"] != evidence_id:
            raise ValueError("lineage evidence_id must match signal evidence")
        con.execute(
            """INSERT INTO prospect_signal_lineage(
                   lineage_id, prospect_id, signal_id, evidence_id, identity_id, offer_id,
                   angle_id, experiment_id, channel_id, recommended_action, outcome_id,
                   revenue_pence, contribution_profit_pence
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                lineage_id, prospect_id, signal_id, evidence_id, identity_id, offer_id,
                angle_id, experiment_id, channel_id, recommended_action, outcome_id,
                revenue_pence, contribution_profit_pence,
            ),
        )


def ranked_prospects(db_path: str, *, limit: int = 10) -> list[dict]:
    """Return explainable ranked buyer candidates; ineligible rows are excluded, not down-ranked."""
    init_signal_store(db_path)
    with connect(db_path) as con:
        rows = con.execute(
            """SELECT s.*, i.identity_id, i.person_name, i.buyer_role, i.status AS identity_status,
                      i.reachable_channel, i.confidence AS identity_confidence
               FROM revenue_intent_signals s
               JOIN identity_resolutions i ON i.prospect_id = s.prospect_id
               ORDER BY s.observed_at DESC, s.strength DESC"""
        ).fetchall()
        suppression = {
            row[0] for row in con.execute("SELECT identity FROM suppression")
        }

    ranked: list[dict] = []
    for row in rows:
        identity_tokens = {row["prospect_id"], row["person_name"], row["company"]}
        candidate = ProspectEligibilityInput(
            prospect_id=row["prospect_id"],
            company=row["company"],
            buyer=row["buyer_role"],
            identity_status=row["identity_status"],
            suppression_clear=not bool(identity_tokens & suppression),
            icp_fit=True,
            hard_disqualifier=False,
            evidence_ids=(row["evidence_id"],),
            reachable_channel=row["reachable_channel"],
        )
        eligibility = ProspectEligibilityGate.evaluate(candidate)
        if not eligibility.eligible:
            continue
        priority = priority_score(PriorityInput(
            icp_fit_score=4,
            signal_strength=row["strength"],
            signal_confidence=row["confidence"],
            observed_at=row["observed_at"],
            evidence_count=1,
            route_quality=4 if row["reachable_channel"] else 1,
        ))
        ranked.append({
            "prospect_id": row["prospect_id"],
            "company": row["company"],
            "person_name": row["person_name"],
            "buyer_role": row["buyer_role"],
            "signal_id": row["signal_id"],
            "signal_type": row["signal_type"],
            "why_now": row["commercial_interpretation"] or row["signal_type"],
            "evidence_id": row["evidence_id"],
            "source": row["source"],
            "priority_score": priority.score,
            "priority_explanation": list(priority.explanation),
            "recommended_channel": row["reachable_channel"],
            "authority": "R3_APPROVAL_REQUIRED",
            "executable": False,
        })
    ranked.sort(key=lambda item: (-item["priority_score"], item["prospect_id"]))
    return ranked[:limit]
