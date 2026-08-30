"""Human-gated outbound workflow for the internal GrowthOps console."""
from __future__ import annotations

from typing import Any, Mapping

from .registry import parse_recipient_class
from .storage import connect, init_db


ALLOWED_CHANNELS = frozenset({"email", "linkedin", "contact_form"})
ACTIVE_DRAFT_STATUSES = ("pending_approval", "approved")
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
               WHERE lower(status) NOT LIKE 'disqualified%'
               ORDER BY CASE priority WHEN 'A' THEN 0 WHEN 'B' THEN 1 ELSE 2 END,
                        company"""
        ).fetchall()
        drafts = con.execute(
            """SELECT id, prospect_id, company, recipient_identity, recipient_class,
                      channel, observation, economic_hypothesis, cta, metric,
                      source_url, message, status, outreach_id, created_at,
                      approved_at, sent_at, replied_at, rejected_at
               FROM outbound_drafts
               ORDER BY id DESC LIMIT 30"""
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
    draft_values = []
    for row in drafts:
        value = dict(row)
        value["signal_ids"] = lineage.get(row["id"], [])
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
        },
        "channels": sorted(ALLOWED_CHANNELS),
        "recipient_classes": ["named_buyer", "role_inbox"],
    }


def create_draft(db_path: str, values: Mapping[str, Any]) -> dict[str, Any]:
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
    if observation.casefold() == hypothesis.casefold():
        raise WorkbenchError("fact_inference_blended", "Observation and hypothesis must differ")
    _validate_low_friction_cta(cta)

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
                 observation, economic_hypothesis, cta, metric, source_url, message
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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


def reject_draft(db_path: str, draft_id: int) -> dict[str, Any]:
    return _transition(
        db_path,
        draft_id,
        from_status="pending_approval",
        to_status="rejected",
        timestamp_column="rejected_at",
    )


def record_manual_send(db_path: str, draft_id: int) -> dict[str, Any]:
    init_db(db_path)
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
                   ) VALUES (?, CURRENT_TIMESTAMP, ?, 'sent_awaiting_reply', ?, ?)""",
                (
                    draft["company"],
                    f"Recorded from approved outbound draft #{draft_id}",
                    draft["recipient_class"],
                    draft["channel"],
                ),
            )
            con.execute(
                """UPDATE outbound_drafts
                   SET status = 'sent', outreach_id = ?, sent_at = CURRENT_TIMESTAMP
                   WHERE id = ?""",
                (outreach.lastrowid, draft_id),
            )
    return get_draft(db_path, draft_id)


def record_meaningful_reply(db_path: str, draft_id: int) -> dict[str, Any]:
    init_db(db_path)
    with connect(db_path) as con:
        draft = _draft_row(con, draft_id)
        if draft["status"] not in {"sent", "replied"} or not draft["outreach_id"]:
            raise WorkbenchError("send_required", "A sent draft is required before recording a reply")
        if draft["status"] == "sent":
            con.execute(
                """UPDATE outreach
                   SET meaningful_reply = 1, stage = 'meaningful_reply'
                   WHERE id = ?""",
                (draft["outreach_id"],),
            )
            con.execute(
                """UPDATE outbound_drafts
                   SET status = 'replied', replied_at = CURRENT_TIMESTAMP
                   WHERE id = ?""",
                (draft_id,),
            )
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
                f"UPDATE outbound_drafts SET status = ?, {timestamp_column} = CURRENT_TIMESTAMP WHERE id = ?",
                (to_status, draft_id),
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
