"""Canonical funnel events — the one record through which marketing activity reaches revenue.

Every commercial fact is one appended row: a send, an acceptance, a reply, a meeting, a
proposal, a payment, a unit of spend. Nothing is updated or deleted; the table refuses both
(triggers in `storage.SCHEMA`). A wrong event is fixed by appending a correction that voids
it, so any past report can be rebuilt from the log exactly as it stood.

Adapters translate existing stores into events. They never supply a field the source does
not carry: a send log with no reply date does not acquire one.
"""
from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Mapping

from .storage import connect, init_db

STAGES: dict[str, tuple[str, ...]] = {
    "attention": ("impression", "video_start", "hook_view", "engagement"),
    "traffic": ("click", "landing_page_view"),
    "outreach": ("message_sent", "message_bounced", "invitation_sent", "invitation_undeliverable",
                 "invitation_accepted", "reply_received", "reply_meaningful"),
    "lead": ("lead_created", "lead_qualified", "lead_disqualified"),
    "sales": ("meeting_booked", "meeting_held", "proposal_sent", "proposal_accepted",
              "proposal_rejected"),
    "customer": ("customer_won", "customer_lost"),
    "revenue": ("payment_received", "recurring_revenue_started", "recurring_revenue_cancelled",
                "refund"),
    "cost": ("spend_recorded",),
}
STAGE_OF = {event_type: stage for stage, types in STAGES.items() for event_type in types}
CORRECTION = "correction"

# Money rides only on events where an amount means something. A value on a click is a typo
# that would later be summed into revenue.
VALUED = frozenset({"proposal_sent", "proposal_accepted", "payment_received",
                    "recurring_revenue_started", "recurring_revenue_cancelled", "refund",
                    "spend_recorded"})
# Platforms report impressions and clicks as counts. A reply, meeting or payment is one fact
# about one buyer and never arrives as a count.
AGGREGATE_STAGES = frozenset({"attention", "traffic"})
# Stages that describe a buyer must name one, or nothing downstream can be traced to them.
ENTITY_STAGES = frozenset({"outreach", "lead", "sales", "customer", "revenue"})
PROVENANCES = ("platform_export", "system_import", "operator_recorded", "synthetic_fixture")
# Invitation outcomes where nothing reached the buyer: an attempt, never an exposure.
BLOCKED_OUTCOMES = frozenset({"undeliverable", "restricted"})
TEXT_FIELDS = ("person_id", "company", "campaign_id", "creative_id", "audience_id", "channel",
               "experiment_id", "arm")


class EventError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def event_id_for(source: str, source_record_id: str, event_type: str) -> str:
    """Deterministic, so re-importing the same source record lands on the same event."""
    digest = hashlib.sha256(f"{source}\x1f{source_record_id}\x1f{event_type}".encode()).hexdigest()
    return f"EVT-{digest[:16]}"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _occurred_at(value: Any) -> str:
    text = str(value or "").strip()
    try:
        datetime.fromisoformat(text)
    except ValueError as exc:
        raise EventError("invalid_occurred_at",
                         f"occurred_at must be an ISO date or datetime, got {text!r}") from exc
    return text


def record_event(db_path: str, values: Mapping[str, Any]) -> dict:
    """Append one event. Returns inserted=False when the same source record was already logged."""
    init_db(db_path)
    event_type = str(values.get("event_type") or "").strip()
    if event_type not in STAGE_OF:
        raise EventError("unknown_event_type", f"unknown event_type {event_type!r}")
    stage = STAGE_OF[event_type]
    source = str(values.get("source") or "").strip()
    source_record_id = str(values.get("source_record_id") or "").strip()
    if not source or not source_record_id:
        raise EventError("missing_source", "an event needs source and source_record_id: an "
                         "unsourced fact cannot be audited or de-duplicated")
    provenance = str(values.get("provenance") or "").strip()
    if provenance not in PROVENANCES:
        raise EventError("invalid_provenance", f"provenance must be one of {', '.join(PROVENANCES)}")
    value = int(values.get("value_pence") or 0)
    currency = str(values.get("currency") or "").strip().upper()
    if value < 0:
        raise EventError("negative_value", "value_pence is a magnitude; the event type carries "
                         "the direction (refund, spend)")
    if value and event_type not in VALUED:
        raise EventError("value_not_allowed", f"{event_type} cannot carry money")
    if value and not currency:
        raise EventError("currency_required", "an amount without a currency cannot be summed")
    quantity = int(values.get("quantity") or 1)
    if quantity < 1:
        raise EventError("invalid_quantity", "quantity must be at least 1")
    if quantity > 1 and stage not in AGGREGATE_STAGES:
        raise EventError("quantity_not_allowed", f"{event_type} is one fact about one buyer; only "
                         "attention and traffic events arrive as counts")
    text = {name: str(values.get(name) or "").strip() for name in TEXT_FIELDS}
    if stage in ENTITY_STAGES and not (text["company"] or text["person_id"]):
        raise EventError("entity_required", f"{event_type} must name the company or person it is about")
    occurred_at = _occurred_at(values.get("occurred_at"))
    company_id = values.get("company_id")
    event_id = event_id_for(source, source_record_id, event_type)
    with connect(db_path) as con:
        existing = con.execute(
            """SELECT e.event_id,
                      EXISTS(SELECT 1 FROM funnel_events c WHERE c.corrects_event_id = e.event_id) AS voided
               FROM funnel_events e WHERE e.event_id = ?""", (event_id,)).fetchone()
        if existing is not None:
            if existing["voided"]:
                raise EventError("voided_event_reused",
                                 f"{event_id} was corrected away; record the new fact under a new "
                                 "source_record_id rather than reviving the voided one")
            return {"event_id": event_id, "event_type": event_type, "inserted": False}
        con.execute(
            """INSERT INTO funnel_events(
                 event_id, event_type, stage, occurred_at, person_id, company_id, company,
                 campaign_id, creative_id, audience_id, channel, experiment_id, arm, source,
                 source_record_id, quantity, value_pence, currency, metadata_json, provenance)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (event_id, event_type, stage, occurred_at, text["person_id"],
             None if company_id in (None, "") else int(company_id), text["company"],
             text["campaign_id"], text["creative_id"], text["audience_id"], text["channel"],
             text["experiment_id"], text["arm"], source, source_record_id, quantity, value,
             currency, json.dumps(dict(values.get("metadata") or {}), sort_keys=True), provenance))
    return {"event_id": event_id, "event_type": event_type, "inserted": True}


def correct_event(db_path: str, event_id: str, reason: str, *, recorded_by: str = "operator") -> dict:
    """Void one event by appending a correction. The original row stays readable."""
    init_db(db_path)
    if not reason.strip():
        raise EventError("reason_required", "a correction without a reason is a deletion")
    with connect(db_path) as con:
        target = con.execute("SELECT event_type FROM funnel_events WHERE event_id = ?",
                             (event_id,)).fetchone()
        if target is None:
            raise EventError("not_found", f"no event {event_id}")
        if target["event_type"] == CORRECTION:
            raise EventError("correction_of_correction",
                             "a correction cannot be corrected; record the right fact as a new event")
        if con.execute("SELECT 1 FROM funnel_events WHERE corrects_event_id = ?", (event_id,)).fetchone():
            raise EventError("already_corrected", f"{event_id} is already corrected")
        correction_id = event_id_for(CORRECTION, event_id, CORRECTION)
        con.execute(
            """INSERT INTO funnel_events(event_id, event_type, stage, occurred_at, source,
                 source_record_id, provenance, corrects_event_id, metadata_json)
               VALUES (?, ?, ?, ?, ?, ?, 'operator_recorded', ?, ?)""",
            (correction_id, CORRECTION, CORRECTION, _utc_now(), CORRECTION, event_id, event_id,
             json.dumps({"reason": reason.strip(), "recorded_by": recorded_by}, sort_keys=True)))
    return {"event_id": correction_id, "corrects_event_id": event_id}


def effective_events(db_path: str, *, include_synthetic: bool = False) -> list[dict]:
    """Every event not voided by a correction. Synthetic fixtures are excluded unless asked
    for, so a demonstration row can never be counted as market validation."""
    init_db(db_path)
    with connect(db_path) as con:
        rows = con.execute(
            """SELECT * FROM funnel_events e
               WHERE e.event_type != 'correction'
                 AND NOT EXISTS (SELECT 1 FROM funnel_events c WHERE c.corrects_event_id = e.event_id)
                 AND (? OR e.provenance != 'synthetic_fixture')
               ORDER BY e.occurred_at, e.event_id""", (int(include_synthetic),)).fetchall()
    events = []
    for row in rows:
        event = dict(row)
        event["metadata"] = json.loads(event.pop("metadata_json") or "{}")
        events.append(event)
    return events


def synthetic_count(db_path: str) -> int:
    init_db(db_path)
    with connect(db_path) as con:
        return con.execute(
            "SELECT COUNT(*) FROM funnel_events WHERE provenance = 'synthetic_fixture'").fetchone()[0]


# --- adapters: existing stores -> canonical events ----------------------------------------

def import_outreach_csv(db_path: str, csv_path: str, *, experiment_id: str,
                        campaign_id: str = "", arm: str = "") -> dict:
    """A send log (date_first_contact, company, recipient, recipient_class, channel, stage,
    message_variant, meaningful_reply) becomes message_sent / message_bounced /
    reply_meaningful events. The log names no experiment, so the operator must."""
    if not experiment_id.strip():
        raise EventError("experiment_required",
                         "a send log carries no experiment id; name the experiment it belongs to")
    init_db(db_path)
    with connect(db_path) as con:
        company_ids = {row["company"]: row["id"] for row in con.execute("SELECT id, company FROM prospects")}
    inserted = already_present = incomplete = 0
    with open(csv_path, newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            company = (row.get("company") or "").strip()
            sent_at = (row.get("date_first_contact") or "").strip()
            if not company or not sent_at:
                incomplete += 1
                continue
            stage = (row.get("stage") or "").strip()
            metadata = {"recipient_class": (row.get("recipient_class") or "").strip(),
                        "role": (row.get("role") or "").strip(), "log_stage": stage,
                        "source_file": str(csv_path)}
            base = {"occurred_at": sent_at, "company": company, "company_id": company_ids.get(company),
                    "person_id": (row.get("recipient") or "").strip(), "campaign_id": campaign_id,
                    "creative_id": (row.get("message_variant") or "").strip(),
                    "channel": (row.get("channel") or "").strip().lower(), "experiment_id": experiment_id,
                    "arm": arm, "source": "outreach_csv",
                    "source_record_id": f"{experiment_id}|{sent_at}|{company}",
                    "provenance": "system_import", "metadata": metadata}
            batch = [dict(base, event_type="message_bounced" if stage == "bounced" else "message_sent")]
            if (row.get("meaningful_reply") or "").strip().lower() in {"1", "true", "yes"}:
                replied_at = (row.get("replied_at") or "").strip()
                batch.append(dict(base, event_type="reply_meaningful", occurred_at=replied_at or sent_at,
                                  metadata=dict(metadata, occurred_at_is_send_date=not replied_at)))
            for values in batch:
                result = record_event(db_path, values)
                inserted += result["inserted"]
                already_present += not result["inserted"]
    return {"inserted": inserted, "already_present": already_present, "incomplete_rows": incomplete}


def _is_effective(db_path: str, event_id: str) -> bool:
    with connect(db_path) as con:
        return con.execute(
            """SELECT 1 FROM funnel_events e WHERE e.event_id = ?
                 AND NOT EXISTS (SELECT 1 FROM funnel_events c WHERE c.corrects_event_id = e.event_id)""",
            (event_id,)).fetchone() is not None


def import_invitations(db_path: str, cohort_id: str, *, experiment_id: str = "",
                       channel: str = "linkedin") -> dict:
    """Invitation outcomes become invitation_sent / invitation_accepted events.

    The invitations table is updated in place, so an acceptance can later read `withdrawn`.
    When that happens the logged acceptance is corrected, not left standing.
    """
    init_db(db_path)
    with connect(db_path) as con:
        members = [dict(row) for row in con.execute(
            """SELECT v.prospect_id, v.outcome, v.submitted_at, v.accepted_at, v.treatment,
                      c.identity_value, p.company
               FROM invitations v
               JOIN execution_cohort c ON c.cohort_id = v.cohort_id AND c.prospect_id = v.prospect_id
               JOIN prospects p ON p.id = v.prospect_id
               WHERE v.cohort_id = ?""", (cohort_id,))]
    inserted = corrected = 0
    for member in members:
        if member["outcome"] == "not_submitted":
            continue
        record_id = f"{cohort_id}|{member['prospect_id']}"
        base = {"company": member["company"], "company_id": member["prospect_id"],
                "person_id": member["identity_value"], "channel": channel,
                "experiment_id": experiment_id or cohort_id, "creative_id": member["treatment"],
                "source": "invitations", "source_record_id": record_id,
                "provenance": "system_import", "metadata": {"outcome": member["outcome"]}}
        sent_id = event_id_for("invitations", record_id, "invitation_sent")
        if member["outcome"] in BLOCKED_OUTCOMES:
            if _is_effective(db_path, sent_id):
                correct_event(db_path, sent_id,
                              f"invitations now reads {member['outcome']!r}: it never reached the buyer, "
                              "so it is an attempt, not an exposure", recorded_by="import_invitations")
                corrected += 1
            inserted += record_event(db_path, dict(base, event_type="invitation_undeliverable",
                                                   occurred_at=member["submitted_at"]))["inserted"]
            continue
        inserted += record_event(db_path, dict(base, event_type="invitation_sent",
                                               occurred_at=member["submitted_at"]))["inserted"]
        accepted_id = event_id_for("invitations", record_id, "invitation_accepted")
        if member["outcome"] == "accepted":
            inserted += record_event(db_path, dict(base, event_type="invitation_accepted",
                                                   occurred_at=member["accepted_at"]))["inserted"]
        elif _is_effective(db_path, accepted_id):
            correct_event(db_path, accepted_id,
                          f"invitations now reads {member['outcome']!r}; the acceptance no longer holds",
                          recorded_by="import_invitations")
            corrected += 1
    return {"members": len(members), "inserted": inserted, "corrected": corrected}
