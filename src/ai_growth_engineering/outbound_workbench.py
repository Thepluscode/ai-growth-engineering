"""Human-gated outbound workflow for the internal GrowthOps console."""
from __future__ import annotations

from typing import Any, Mapping

from .registry import parse_recipient_class
from .funnel_events import effective_events, observed_time, record_event
from .storage import connect, init_db


ALLOWED_CHANNELS = frozenset({"email", "linkedin", "contact_form"})
ACTIVE_DRAFT_STATUSES = ("pending_approval", "approved")

# Route states, derived from the draft and its recorded events - never typed in.
# Qualified is not send-ready: a name to look up later is not a route.
ROUTE_UNVERIFIED = "ROUTE_UNVERIFIED"      # a name only
PROFILE_VERIFIED = "PROFILE_VERIFIED"      # verified profile link: a connection request is possible
DIRECT_VERIFIED = "DIRECT_VERIFIED"        # published email, or an accepted 1st-degree connection
# What counts as evidence that a message reached the named buyer, recorded separately from the
# send by `record_delivery`. "We sent it" - even to an accepted connection - is not on the list:
# a send never manufactures its own delivery. A reply also proves delivery (see demand_funnel).
DELIVERY_EVIDENCE = frozenset({
    "linkedin_seen_indicator",             # LinkedIn showed the message as Seen by the recipient
})
HIGH_FRICTION_CTA_PHRASES = (
    "book a call",
    "book time",
    "schedule a call",
    "schedule a meeting",
    "calendar link",
    "buy now",
    "sign up",
)


class WorkbenchError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def workbench_state(db_path: str) -> dict[str, Any]:
    init_db(db_path)
    with connect(db_path) as con:
        prospects = con.execute(
            """SELECT id, company, website, priority, target_roles, evidence,
                      source_url, status
               FROM prospects
               -- Qualified by assertion, not by omission. This read
               -- `NOT LIKE 'disqualified%'`, which made the workbench's prospect list
               -- accept every state that was not an explicit refusal — `research`,
               -- `ready_for_deep_research`, and any later `candidate` or `pending`
               -- import. An account nobody qualified would have appeared here as
               -- somebody to approach, which is the lineage rule broken at the last
               -- step before contact.
               WHERE status LIKE 'qualified%'
               ORDER BY CASE priority WHEN 'A' THEN 0 WHEN 'B' THEN 1 ELSE 2 END,
                        company"""
        ).fetchall()
        drafts = con.execute(
            """SELECT id, prospect_id, company, recipient_identity, recipient_class,
                      channel, observation, economic_hypothesis, cta, metric,
                      source_url, message, status, outreach_id, created_at,
                      approved_at, sent_at, replied_at, rejected_at, experiment_id,
                      subject, status_reason, held_at, route_evidence_url, route_verified_at,
                      route_verification
               FROM outbound_drafts
               ORDER BY CASE status
                          WHEN 'approved' THEN 0
                          WHEN 'pending_approval' THEN 1
                          WHEN 'sent' THEN 2
                          WHEN 'replied' THEN 3
                          WHEN 'held' THEN 4
                          ELSE 5
                        END,
                        id DESC"""
        ).fetchall()
        counts = {
            row["status"]: row["count"]
            for row in con.execute(
                "SELECT status, COUNT(*) AS count FROM outbound_drafts GROUP BY status"
            )
        }
        lineage: dict[int, list[str]] = {}
        for row in con.execute(
            "SELECT draft_id, signal_id FROM draft_signal_lineage ORDER BY created_at, signal_id"
        ):
            lineage.setdefault(row["draft_id"], []).append(row["signal_id"])
    event_types: dict[int, set[str]] = {}
    for event in effective_events(db_path):
        source_record_id = str(event.get("source_record_id") or "")
        if event.get("source") != "workbench" or not source_record_id.startswith("draft-"):
            continue
        try:
            draft_id = int(source_record_id.removeprefix("draft-"))
        except ValueError:
            continue
        event_types.setdefault(draft_id, set()).add(str(event["event_type"]))
    draft_values = []
    for row in drafts:
        value = dict(row)
        value["signal_ids"] = lineage.get(row["id"], [])
        value["event_types"] = sorted(event_types.get(row["id"], set()))
        value["route_status"] = _route_status(value, event_types.get(row["id"], set()))
        draft_values.append(value)
    return {
        "prospects": [dict(row) for row in prospects],
        "drafts": draft_values,
        "counts": {
            "pending_approval": counts.get("pending_approval", 0),
            "approved": counts.get("approved", 0),
            "sent": counts.get("sent", 0),
            "replied": counts.get("replied", 0),
            "rejected": counts.get("rejected", 0),
            "held": counts.get("held", 0),
        },
        "total_drafts": sum(counts.values()),
        "channels": sorted(ALLOWED_CHANNELS),
        "recipient_classes": ["named_buyer", "role_inbox"],
    }


def create_draft(db_path: str, values: Mapping[str, Any], *,
                 route_verification: Mapping[str, str] | None = None) -> dict[str, Any]:
    """`route_verification` is keyword-only so a request body can never supply it: only code that
    fetched the page and found the exact address there (marketer.verify) may vouch for an email."""
    init_db(db_path)
    prospect_id = _positive_int(values.get("prospect_id"), "prospect_id")
    identity = _required(values, "recipient_identity", 3, 320)
    recipient_class = parse_recipient_class(
        _required(values, "recipient_class", 3, 40)
    )
    if recipient_class == "unclassified":
        raise WorkbenchError("recipient_class_required", "Choose named buyer or role inbox")
    channel = _required(values, "channel", 3, 40).lower().replace("-", "_")
    if channel not in ALLOWED_CHANNELS:
        raise WorkbenchError(
            "invalid_channel", f"Channel must be one of {', '.join(sorted(ALLOWED_CHANNELS))}"
        )
    observation = _required(values, "observation", 30, 1200)
    hypothesis = _required(values, "economic_hypothesis", 30, 1200)
    cta = _required(values, "cta", 5, 180)
    metric = _required(values, "metric", 3, 120)
    source_url = _required(values, "source_url", 8, 800)
    signal_ids = _signal_ids(values.get("signal_ids"))
    if not source_url.startswith(("https://", "http://")):
        raise WorkbenchError("invalid_source", "Observed claims require an http(s) source URL")
    route = dict(route_verification or {})
    if route and not (str(route.get("url", "")).startswith(("https://", "http://"))
                      and route.get("verified_at") and route.get("method")):
        raise WorkbenchError("invalid_route_evidence",
                             "Route verification needs the http(s) page, when it was checked and how")
    if observation.casefold() == hypothesis.casefold():
        raise WorkbenchError("fact_inference_blended", "Observation and hypothesis must differ")
    _validate_low_friction_cta(cta)
    experiment_id = str(values.get("experiment_id") or "").strip()
    if experiment_id:
        from . import registries

        if not any(link["experiment_id"] == experiment_id
                   for link in registries.rows(db_path, "market_experiments")):
            raise WorkbenchError("experiment_not_linked",
                                 f"{experiment_id} is not linked to any market; its sends would count nowhere")
        # EXP-ACQ-0001 sent 48 of 50 to shared inboxes and tested access, not the message.
        if recipient_class != "named_buyer":
            raise WorkbenchError("named_buyer_required",
                                 "A market experiment counts named buyers only; a role inbox is not an exposure")

    with connect(db_path) as con:
        prospect = con.execute(
            "SELECT id, company, status FROM prospects WHERE id = ?", (prospect_id,)
        ).fetchone()
        if prospect is None:
            raise WorkbenchError("prospect_not_found", "Prospect does not exist")
        if prospect["status"].lower().startswith("disqualified"):
            raise WorkbenchError("prospect_disqualified", "Disqualified prospects cannot enter outreach")
        if signal_ids:
            rows = con.execute(
                f"""SELECT signal_id, prospect_id FROM intent_signals
                    WHERE signal_id IN ({','.join('?' for _ in signal_ids)})""",
                signal_ids,
            ).fetchall()
            found = {row["signal_id"]: row["prospect_id"] for row in rows}
            missing = [signal_id for signal_id in signal_ids if signal_id not in found]
            if missing:
                raise WorkbenchError("signal_not_found", f"Intent signal does not exist: {missing[0]}")
            if any(found[signal_id] != prospect_id for signal_id in signal_ids):
                raise WorkbenchError(
                    "signal_prospect_mismatch", "Every linked signal must belong to the selected prospect"
                )
        suppressed = con.execute(
            "SELECT reason FROM suppression WHERE lower(identity) = lower(?)", (identity,)
        ).fetchone()
        if suppressed:
            raise WorkbenchError("suppressed", f"Recipient is suppressed: {suppressed['reason']}")
        duplicate = con.execute(
            """SELECT id FROM outbound_drafts
               WHERE company = ? AND lower(recipient_identity) = lower(?)
                 AND status IN (?, ?)""",
            (prospect["company"], identity, *ACTIVE_DRAFT_STATUSES),
        ).fetchone()
        if duplicate:
            raise WorkbenchError(
                "active_draft_exists", f"Active draft #{duplicate['id']} already targets this recipient"
            )
        message = f"{observation}\n\n{hypothesis}\n\n{cta}"
        con.execute(
            "INSERT INTO teardowns(company, observation, hypothesis, metric) VALUES (?, ?, ?, ?)",
            (prospect["company"], observation, hypothesis, metric),
        )
        cursor = con.execute(
            """INSERT INTO outbound_drafts(
                 prospect_id, company, recipient_identity, recipient_class, channel,
                 observation, economic_hypothesis, cta, metric, source_url, message, experiment_id, subject,
                 route_evidence_url, route_verified_at, route_verification
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                prospect_id,
                prospect["company"],
                identity,
                recipient_class,
                channel,
                observation,
                hypothesis,
                cta,
                metric,
                source_url,
                message,
                experiment_id,
                str(values.get("subject") or "").strip()[:160],
                str(route.get("url", ""))[:800],
                route.get("verified_at"),
                str(route.get("method", ""))[:400],
            ),
        )
        draft_id = cursor.lastrowid
        con.executemany(
            "INSERT INTO draft_signal_lineage(draft_id, signal_id) VALUES (?, ?)",
            ((draft_id, signal_id) for signal_id in signal_ids),
        )
    return get_draft(db_path, draft_id)


def approve_draft(db_path: str, draft_id: int) -> dict[str, Any]:
    return _transition(
        db_path,
        draft_id,
        from_status="pending_approval",
        to_status="approved",
        timestamp_column="approved_at",
    )


def reject_draft(db_path: str, draft_id: int, reason: str = "") -> dict[str, Any]:
    return _transition(
        db_path,
        draft_id,
        from_status="pending_approval",
        to_status="rejected",
        timestamp_column="rejected_at",
        reason=reason,
    )


def hold_draft(db_path: str, draft_id: int, reason: str) -> dict[str, Any]:
    """Out of the active queue and impossible to approve or send, but kept: a held draft is a
    historical artefact until it is re-qualified under the current rules."""
    if len(reason.strip()) < 5:
        raise WorkbenchError("reason_required", "say why the draft is held")
    return _transition(db_path, draft_id, from_status="pending_approval", to_status="held",
                       timestamp_column="held_at", reason=reason)


def _draft_events(db_path: str, draft_id: int) -> set[str]:
    return {e["event_type"] for e in effective_events(db_path)
            if e["source"] == "workbench" and e["source_record_id"] == f"draft-{draft_id}"}


def route_status(db_path: str, draft: Mapping[str, Any]) -> str:
    return _route_status(draft, _draft_events(db_path, int(draft["id"])))


def _route_status(draft: Mapping[str, Any], event_types: set[str]) -> str:
    identity = str(draft["recipient_identity"])
    if draft["channel"] == "email" and "@" in identity and " " not in identity:
        # An address is only a route if a fetched page published it; a well-formed guess is not.
        keys = draft.keys()
        verified = all(k in keys and draft[k] for k in ("route_evidence_url", "route_verified_at"))
        return DIRECT_VERIFIED if verified else ROUTE_UNVERIFIED
    if not identity.startswith("https://"):
        return ROUTE_UNVERIFIED
    if "invitation_accepted" in event_types:
        return DIRECT_VERIFIED
    return PROFILE_VERIFIED


def record_connection_request(db_path: str, draft_id: int, sent_at: Any = "") -> dict[str, Any]:
    """A short connection note to obtain access. It is not the experiment's message and never
    counts as a send or a delivery."""
    sent_at = _observed(sent_at, "when the connection request was sent")
    draft = get_draft(db_path, draft_id)
    if draft["status"] != "approved":
        raise WorkbenchError("approval_required", "Approve the draft before contacting the buyer")
    if draft["channel"] != "linkedin" or route_status(db_path, draft) != PROFILE_VERIFIED:
        raise WorkbenchError("route_not_connectable",
                             "a connection request needs a verified profile link and no accepted connection yet")
    record_event(db_path, {**_draft_event(draft), "event_type": "invitation_sent", "occurred_at": sent_at})
    return draft


def record_connection_accepted(db_path: str, draft_id: int, accepted_at: Any = "") -> dict[str, Any]:
    """Only once they are 1st-degree with the Message action available."""
    accepted_at = _observed(accepted_at, "when the connection was accepted")
    draft = get_draft(db_path, draft_id)
    if "invitation_sent" not in _draft_events(db_path, draft_id):
        raise WorkbenchError("request_required", "record the connection request first")
    record_event(db_path, {**_draft_event(draft), "event_type": "invitation_accepted", "occurred_at": accepted_at})
    return draft


def record_delivery(db_path: str, draft_id: int, delivered_at: Any, evidence: str) -> dict[str, Any]:
    delivered_at = _observed(delivered_at, "when delivery was observed")
    if evidence not in DELIVERY_EVIDENCE:
        raise WorkbenchError("delivery_evidence_required",
                             f"delivery needs evidence, one of {', '.join(sorted(DELIVERY_EVIDENCE))}")
    draft = get_draft(db_path, draft_id)
    if draft["status"] not in {"sent", "replied"}:
        raise WorkbenchError("send_required", "A sent draft is required before recording delivery")
    event = _draft_event(draft)
    record_event(db_path, {**event, "event_type": "message_delivered", "occurred_at": delivered_at,
                           "metadata": {**event["metadata"], "delivery_evidence": evidence}})
    return draft


def _observed(value: Any, what: str) -> str:
    try:
        text = observed_time(value)
    except ValueError as exc:
        raise WorkbenchError("invalid_timestamp", f"{what} must be an ISO date or datetime") from exc
    if not text:
        raise WorkbenchError("observed_time_required",
                             f"record {what}; the moment of clicking is not when it happened")
    return text


def record_manual_send(db_path: str, draft_id: int, sent_at: Any = "") -> dict[str, Any]:
    sent_at = _observed(sent_at, "when the message was sent")
    init_db(db_path)
    with connect(db_path) as con:
        draft = _draft_row(con, draft_id)
    if draft["status"] == "approved" and draft["experiment_id"] and route_status(db_path, draft) != DIRECT_VERIFIED:
        # A market experiment measures demand among buyers who were actually reachable.
        raise WorkbenchError("route_unverified",
                             "no verified direct route: a published email, or an accepted 1st-degree "
                             "LinkedIn connection with the Message action available")
    with connect(db_path) as con:
        draft = _draft_row(con, draft_id)
        if draft["status"] not in {"approved", "sent"}:
            raise WorkbenchError("approval_required", "Approve the draft before recording a send")
        if draft["status"] == "approved":
            suppressed = con.execute(
                "SELECT reason FROM suppression WHERE lower(identity) = lower(?)",
                (draft["recipient_identity"],),
            ).fetchone()
            if suppressed:
                raise WorkbenchError("suppressed", f"Recipient is suppressed: {suppressed['reason']}")
            outreach = con.execute(
                """INSERT INTO outreach(
                     company, sent_at, notes, stage, recipient_class, channel
                   ) VALUES (?, ?, ?, 'sent_awaiting_reply', ?, ?)""",
                (
                    draft["company"],
                    sent_at,
                    f"Recorded from approved outbound draft #{draft_id}",
                    draft["recipient_class"],
                    draft["channel"],
                ),
            )
            con.execute(
                """UPDATE outbound_drafts
                   SET status = 'sent', outreach_id = ?, sent_at = ?
                   WHERE id = ?""",
                (outreach.lastrowid, sent_at, draft_id),
            )
            first_send = True
        else:
            first_send = False
    if first_send:
        record_event(db_path, {**_draft_event(draft), "event_type": "message_sent", "occurred_at": sent_at})
    return get_draft(db_path, draft_id)


def _draft_event(draft) -> dict[str, Any]:
    """The canonical identity of a workbench draft's outcomes. The recipient class was chosen by the
    operator when the draft was written, so it is observed."""
    return {"company": draft["company"], "company_id": draft["prospect_id"],
            "person_id": draft["recipient_identity"], "channel": draft["channel"],
            "experiment_id": draft["experiment_id"],
            "source": "workbench", "source_record_id": f"draft-{draft['id']}",
            "provenance": "operator_recorded", "metadata": {"recipient_class": draft["recipient_class"]}}


def record_meaningful_reply(db_path: str, draft_id: int, replied_at: Any = "") -> dict[str, Any]:
    replied_at = _observed(replied_at, "when the reply arrived")
    init_db(db_path)
    with connect(db_path) as con:
        draft = _draft_row(con, draft_id)
        if draft["status"] not in {"sent", "replied"} or not draft["outreach_id"]:
            raise WorkbenchError("send_required", "A sent draft is required before recording a reply")
        if replied_at[:10] < str(draft["sent_at"] or "")[:10]:
            raise WorkbenchError("reply_before_send", "a reply cannot arrive before the message it answers")
        first_reply = draft["status"] == "sent"
        if first_reply:
            con.execute(
                """UPDATE outreach
                   SET meaningful_reply = 1, stage = 'meaningful_reply'
                   WHERE id = ?""",
                (draft["outreach_id"],),
            )
            con.execute(
                """UPDATE outbound_drafts
                   SET status = 'replied', replied_at = ?
                   WHERE id = ?""",
                (replied_at, draft_id),
            )
    if first_reply:
        record_event(db_path, {**_draft_event(draft), "event_type": "reply_meaningful", "occurred_at": replied_at})
    return get_draft(db_path, draft_id)


def get_draft(db_path: str, draft_id: int) -> dict[str, Any]:
    init_db(db_path)
    with connect(db_path) as con:
        value = dict(_draft_row(con, draft_id))
        value["signal_ids"] = [
            row["signal_id"]
            for row in con.execute(
                "SELECT signal_id FROM draft_signal_lineage WHERE draft_id = ? ORDER BY created_at, signal_id",
                (draft_id,),
            )
        ]
        return value


def _transition(
    db_path: str,
    draft_id: int,
    *,
    from_status: str,
    to_status: str,
    timestamp_column: str,
    reason: str = "",
) -> dict[str, Any]:
    init_db(db_path)
    with connect(db_path) as con:
        draft = _draft_row(con, draft_id)
        if draft["status"] not in {from_status, to_status}:
            raise WorkbenchError(
                "invalid_transition",
                f"Draft is {draft['status']}; expected {from_status}",
            )
        if draft["status"] == from_status:
            con.execute(
                f"""UPDATE outbound_drafts SET status = ?, {timestamp_column} = CURRENT_TIMESTAMP,
                       status_reason = ? WHERE id = ?""",
                (to_status, reason.strip(), draft_id),
            )
    return get_draft(db_path, draft_id)


def _draft_row(con: Any, draft_id: int) -> Any:
    row = con.execute("SELECT * FROM outbound_drafts WHERE id = ?", (draft_id,)).fetchone()
    if row is None:
        raise WorkbenchError("draft_not_found", "Draft does not exist")
    return row


def _positive_int(value: Any, name: str) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise WorkbenchError("invalid_field", f"{name} must be an integer") from exc
    if number <= 0:
        raise WorkbenchError("invalid_field", f"{name} must be positive")
    return number


def _required(values: Mapping[str, Any], name: str, minimum: int, maximum: int) -> str:
    value = str(values.get(name) or "").strip()
    if len(value) < minimum:
        raise WorkbenchError("invalid_field", f"{name} must be at least {minimum} characters")
    if len(value) > maximum:
        raise WorkbenchError("invalid_field", f"{name} must be at most {maximum} characters")
    return value


def _validate_low_friction_cta(cta: str) -> None:
    if not cta.endswith("?"):
        raise WorkbenchError("cta_not_low_friction", "CTA must be a single low-friction question")
    lowered = cta.casefold()
    blocked = next((phrase for phrase in HIGH_FRICTION_CTA_PHRASES if phrase in lowered), None)
    if blocked:
        raise WorkbenchError(
            "cta_not_low_friction", f"CTA contains high-friction request: {blocked}"
        )


def _signal_ids(value: Any) -> list[str]:
    if value in (None, ""):
        return []
    if not isinstance(value, list):
        raise WorkbenchError("invalid_field", "signal_ids must be a list")
    signal_ids = []
    for item in value:
        signal_id = str(item).strip()
        if not _valid_signal_id(signal_id):
            raise WorkbenchError("invalid_field", "signal_ids contains an invalid signal ID")
        if signal_id not in signal_ids:
            signal_ids.append(signal_id)
    if len(signal_ids) > 20:
        raise WorkbenchError("invalid_field", "A draft may link at most 20 intent signals")
    return signal_ids


def _valid_signal_id(value: str) -> bool:
    return value.startswith("SIG-") and len(value) == 16 and value[4:].isalnum()
