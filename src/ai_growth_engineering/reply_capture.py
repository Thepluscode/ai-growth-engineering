"""Reply capture: a real inbound message becomes a reviewable proposal, never a recorded fact.

    source adapter -> inbound message -> deterministic identity match -> reply candidate
    -> human review, item by item (approve / edit / reject) -> the existing append-only stores

Capture writes only to `reply_candidates`. A funnel event or a piece of buyer evidence is written
by `approve` alone, and only through `record_event` and `record_commercial_evidence`. The rules
below propose; a person decides. The candidate model is channel-neutral: Gmail is one adapter,
and a LinkedIn or manual adapter produces the same inbound-message shape.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Iterable

from .buyer_truth import CATEGORIES, MIN_OBSERVATION_WORDS, BuyerTruthError, record_commercial_evidence
from .funnel_events import EventError, effective_events, event_id_for, record_event
from .revenue_loop import entity
from .storage import connect, init_db


class ReplyCaptureError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


# --- adapters ---------------------------------------------------------------------------

ADDRESS = re.compile(r"[A-Za-z0-9._%+'-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def _address(value) -> str:
    found = ADDRESS.search(str(value or ""))
    return found.group(0).lower() if found else ""


def _iso(value) -> str:
    text = str(value or "").strip()
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(timezone.utc).isoformat(timespec="seconds")
    except ValueError as exc:
        raise ReplyCaptureError("invalid_date", f"message date {text!r} is not ISO 8601") from exc


def gmail_messages(payload) -> list[dict]:
    """Inbound-message records from Gmail thread or search payloads as the Gmail connector returns
    them: {"threads": [...]}, one thread {"id", "messages"}, or a list of either."""
    threads = payload if isinstance(payload, list) else payload.get("threads") or [payload]
    messages = []
    for thread in threads:
        for m in thread.get("messages") or []:
            body = m.get("plaintextBody") or m.get("plaintext_body")
            messages.append({
                "source": "gmail", "source_record_id": str(m["id"]),
                "source_thread_id": str(m.get("threadId") or m.get("thread_id") or thread.get("id") or ""),
                "sender": _address(m.get("sender")),
                "recipients": [_address(r) for r in (m.get("toRecipients") or m.get("to_recipients") or [])],
                "subject": str(m.get("subject") or ""), "occurred_at": _iso(m.get("date")),
                "body": str(body if body is not None else m.get("snippet") or ""),
                # A snippet is truncated and HTML-escaped: enough to see that someone replied,
                # never enough to cite what they said.
                "body_is_snippet": body is None,
                "labels": list(m.get("labelIds") or m.get("label_ids") or []),
            })
    return messages


def link_outbound(db_path: str, records: Iterable[dict]) -> dict:
    """Record which buyer and experiment each governed sent message belongs to."""
    init_db(db_path)
    inserted = present = 0
    with connect(db_path) as con:
        for r in records:
            values = {k: str(r.get(k) or "").strip() for k in ("message_id", "thread_id", "recipient", "company",
                                                               "person_id", "experiment_id", "campaign_id", "sent_at")}
            values["recipient"] = _address(values["recipient"])
            missing = [k for k in ("message_id", "thread_id", "recipient", "company", "experiment_id", "sent_at") if not values[k]]
            if missing:
                raise ReplyCaptureError("outbound_incomplete", f"outbound record lacks {missing}: a send without its "
                                        "source message cannot be linked, however it was counted elsewhere")
            values["sent_at"] = _iso(values["sent_at"])
            existing = con.execute("SELECT company, experiment_id FROM outbound_messages WHERE message_id = ?",
                                   (values["message_id"],)).fetchone()
            if existing:
                if (existing["company"], existing["experiment_id"]) != (values["company"], values["experiment_id"]):
                    raise ReplyCaptureError("outbound_conflict", f"{values['message_id']} is already linked to another buyer")
                present += 1
                continue
            con.execute(
                """INSERT INTO outbound_messages(message_id, source, thread_id, recipient, company, person_id,
                     experiment_id, campaign_id, sent_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (values["message_id"], str(r.get("source") or "gmail"), values["thread_id"], values["recipient"],
                 values["company"], values["person_id"], values["experiment_id"], values["campaign_id"], values["sent_at"]))
            inserted += 1
    return {"inserted": inserted, "already_present": present}


# Shared mailboxes: a send to one of these reached an inbox, not a named person.
ROLE_INBOXES = frozenset({"info", "enquiries", "enquiry", "sales", "hello", "office", "reception", "admin", "support",
                          "contact", "help", "accounts", "team", "service", "services", "bookings"})


def import_outbound_sends(db_path: str, experiment_id: str) -> dict:
    """One `message_sent` per linked, verified outbound message of one experiment. Only a linked
    message — a real message id in a real thread — becomes a send: this function takes no count,
    so a total claimed elsewhere can never create one. Idempotent on the message id."""
    init_db(db_path)
    with connect(db_path) as con:
        rows = [dict(r) for r in con.execute("SELECT * FROM outbound_messages WHERE experiment_id = ? "
                                             "ORDER BY sent_at, message_id", (experiment_id,))]
        campaigns = {r["campaign_id"]: r["offer_id"] for r in con.execute(
            "SELECT campaign_id, offer_id FROM campaigns WHERE experiment_id = ?", (experiment_id,))}
    if not rows:
        raise ReplyCaptureError("no_linked_sends", f"no governed outbound message is linked for {experiment_id}")
    owners: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        owners[row["recipient"]].add(row["company"])
    # A buyer already counted from another source (a send log) is never counted a second time.
    elsewhere = {(entity(e), e["experiment_id"]) for e in effective_events(db_path, include_synthetic=True)
                 if e["event_type"] in ("message_sent", "message_bounced") and e["source"] != "gmail"}
    inserted = present = 0
    refused = []
    for row in rows:
        if len(owners[row["recipient"]]) > 1:
            refused.append({"message_id": row["message_id"], "code": "ambiguous_lineage",
                            "reason": f"the recipient is linked to {len(owners[row['recipient']])} companies in {experiment_id}"})
            continue
        if (row["company"].lower(), experiment_id) in elsewhere:
            refused.append({"message_id": row["message_id"], "code": "recorded_from_other_source",
                            "reason": "this buyer's send is already in the funnel from another source"})
            continue
        campaign = row["campaign_id"] or (next(iter(campaigns)) if len(campaigns) == 1 else "")
        metadata = {"source_thread_id": row["thread_id"],
                    "recipient_class": "role_inbox" if row["recipient"].partition("@")[0] in ROLE_INBOXES else "named_buyer",
                    "recipient_class_basis": "recipient address local part", "offer_id": campaigns.get(campaign, "")}
        if campaign and not row["campaign_id"]:
            metadata["campaign_linked_by"] = "experiment_id"
        result = record_event(db_path, {
            "event_type": "message_sent", "company": row["company"], "person_id": row["person_id"],
            "experiment_id": experiment_id, "campaign_id": campaign, "channel": "email", "source": row["source"],
            "source_record_id": row["message_id"], "occurred_at": row["sent_at"], "provenance": "platform_export",
            "metadata": metadata})
        inserted += result["inserted"]
        present += not result["inserted"]
    return {"experiment_id": experiment_id, "linked": len(rows), "inserted": inserted, "already_present": present,
            "refused": refused}


# --- deterministic reading --------------------------------------------------------------

AUTOMATED_SENDER = re.compile(r"^(mailer-daemon|postmaster|no-?reply|do-?not-?reply|bounces?|auto-?reply|notifications?)@", re.I)
BOUNCE_SENDER = re.compile(r"^(mailer-daemon|postmaster)@", re.I)
BOUNCE_TEXT = re.compile(r"undeliver|delivery status notification|delivery (has )?failed|mail delivery (subsystem|failed)|"
                         r"returned mail|address not found|couldn't be delivered|message not delivered", re.I)
OUT_OF_OFFICE = re.compile(r"out of (the )?office|automatic reply|auto-?reply|away from (the|my) (office|desk)|"
                           r"on (annual )?leave|currently away|limited access to (my )?e-?mail", re.I)
GATEWAY = re.compile(r"auto-?response|has been quarantined|held for review|we have received your (email|message|enquiry)|"
                     r"thank you for contacting|this is an automated (message|response|reply)|ticket (number|#|has been created)", re.I)
UNSUBSCRIBE = re.compile(r"\b(unsubscribe|remove me|take me off|stop emailing|do not contact)\b", re.I)
QUOTE_HEADER = re.compile(r"^(On\b[^\n]*(\n[^\n]*)?wrote:|-{2,}\s*Original Message\s*-{2,}|From:\s.+|Sent from my \w+|_{5,})\s*$",
                          re.I | re.M)
CLAUSE_BOUNDARY = re.compile(r"(?<=[.!?])\s+|\n+|;\s*|,\s*(?=(?:but|however|although|though)\b)", re.I)
CLAUSE_LEAD = re.compile(r"^(?:but|however|although|though)\s+", re.I)
ACKNOWLEDGEMENT_WORDS = frozenset({"thanks", "thank", "cheers", "noted", "received", "ok", "okay", "great", "many"})
MEANINGFUL_CUES = (
    ("discussion requested", re.compile(r"\b(discuss|call|meet|meeting|speak|chat|catch up|book(ing)?|calendar)\b", re.I)),
    ("problem or active evaluation stated", re.compile(r"\b(we are reviewing|we're reviewing|we are looking|we're looking|"
                                                      r"we struggle|our (problem|challenge|issue))\b", re.I)),
)
INFORMATION_REQUEST = re.compile(r"\b(send (me|us|it|over|through|the)|share (it|the|more)|more (details|information))\b", re.I)
# Each rule proposes a category from wording alone. It never decides one: a person reads the clause.
EVIDENCE_RULES = (
    ("REASON_FOR_REJECTION", re.compile(r"\b(not interested|no thanks|not for us|already (have|use|got)|covered internally|"
                                        r"handled internally|not the right time|please remove)\b", re.I)),
    ("REASON_FOR_INTEREST", re.compile(r"\b(?<!not )(interested|interesting|keen|sounds (good|useful)|would like to (learn|hear|see))\b", re.I)),
    ("PROBLEM_STATED", re.compile(r"\b(we (struggle|are struggling)|we have (a|an) (problem|issue)|our (problem|challenge|issue)|"
                                  r"pain point|loses?|losing|wastes?|wasting|keeps? (failing|breaking|slipping))\b", re.I)),
    ("PAIN_CONFIRMED", re.compile(r"\b(that is exactly|that's exactly|spot on|this is (a|our) (real )?(problem|issue))\b", re.I)),
    ("OBJECTION", re.compile(r"\b(can't|cannot|can not|unable to|won't|concern(ed)?|worried|too (expensive|busy|early)|"
                             r"not a priority)\b", re.I)),
    ("BUYING_CRITERION", re.compile(r"\b(need to|needs to|we'd need|would need|must|require(s|d)?|only if|as long as)\b", re.I)),
    ("AUTHORITY_SIGNAL", re.compile(r"\b(handled by|responsible for|speak to|talk to|forward(ed)? (this|it) to|"
                                    r"not my (area|decision)|decision maker|our (compliance|it|security|ops|finance|procurement) team)\b", re.I)),
    ("BUDGET_SIGNAL", re.compile(r"\b(budget|afford|spend)\b", re.I)),
    ("URGENCY_SIGNAL", re.compile(r"\b(urgent|asap|this (week|month|quarter)|right now|currently reviewing)\b", re.I)),
    ("WILLINGNESS_TO_PAY_STATED", re.compile(r"\b(happy to pay|would pay|willing to pay|worth paying)\b", re.I)),
    ("PROPOSAL_REQUESTED", re.compile(r"\b(proposal|quote|quotation|pricing|price list)\b", re.I)),
    # A named alternative only: "we use Acme". "We have it covered" names nothing.
    ("ALTERNATIVE_MENTIONED", re.compile(r"(?i:\b(?:we (?:already )?use|we work with|we're using|we are using))\s+[A-Z][\w&.-]+")),
)


def strip_quoted(body: str) -> str:
    """The new text of a message: everything from the first quote header on, and every quoted
    line, is removed, so a buyer's earlier words quoted back are never read twice."""
    text = body.replace("\r\n", "\n")
    header = QUOTE_HEADER.search(text)
    if header:
        text = text[:header.start()]
    return "\n".join(line for line in text.split("\n") if not line.lstrip().startswith(">")).strip()


def clauses(text: str) -> list[str]:
    """Clauses that are exact substrings of the text, long enough to be an observation."""
    pieces, start = [], 0
    for boundary in CLAUSE_BOUNDARY.finditer(text):
        pieces.append(text[start:boundary.start()])
        start = boundary.end()
    pieces.append(text[start:])
    found = []
    for piece in pieces:
        clause = CLAUSE_LEAD.sub("", piece.strip()).strip()
        if len(clause.split()) >= MIN_OBSERVATION_WORDS:
            found.append(clause)
    return found


def _kind(message: dict, new_text: str) -> str:
    sender, subject, head = message["sender"], message["subject"], message["body"][:800]
    if BOUNCE_SENDER.match(sender) or BOUNCE_TEXT.search(subject):
        return "BOUNCE"
    if OUT_OF_OFFICE.search(subject) or OUT_OF_OFFICE.search(head):
        return "OUT_OF_OFFICE"
    if AUTOMATED_SENDER.match(sender) or GATEWAY.search(subject) or GATEWAY.search(head):
        return "AUTOMATED"
    if UNSUBSCRIBE.search(new_text) and len(new_text.split()) <= 25:
        return "UNSUBSCRIBE"
    return "BUYER_REPLY"


def _domain(address: str) -> str:
    return address.rpartition("@")[2]


def _match(con, message: dict, kind: str) -> dict:
    """Identity from recorded lineage only: the governed thread, or an exact sender address with one
    buyer behind it. A shared domain is never enough."""
    in_thread = [dict(r) for r in con.execute(
        "SELECT * FROM outbound_messages WHERE source = ? AND thread_id = ?",
        (message["source"], message["source_thread_id"]))] if message["source_thread_id"] else []
    if in_thread:
        buyers = {(r["company"], r["experiment_id"]) for r in in_thread}
        if len(buyers) > 1:
            return {"state": "AMBIGUOUS", "note": f"the thread holds governed sends to {len(buyers)} buyers"}
        recipients = {r["recipient"] for r in in_thread}
        first = in_thread[0]
        base = {"state": "MATCHED", "company": first["company"], "experiment_id": first["experiment_id"],
                "campaign_id": first["campaign_id"]}
        if message["sender"] in recipients:
            return {**base, "method": "thread_lineage", "confidence": "HIGH", "person_id": first["person_id"]}
        if kind != "BUYER_REPLY":
            return {**base, "method": "thread_lineage_automated", "confidence": "HIGH", "person_id": ""}
        if _domain(message["sender"]) in {_domain(r) for r in recipients}:
            return {**base, "method": "thread_lineage_same_domain", "confidence": "MEDIUM", "person_id": "",
                    "note": "a different person at the buyer's domain replied in the governed thread"}
        return {"state": "AMBIGUOUS", "note": "someone outside the buyer's domain replied in the governed thread"}
    by_address = [dict(r) for r in con.execute("SELECT * FROM outbound_messages WHERE recipient = ?", (message["sender"],))]
    buyers = {(r["company"], r["experiment_id"]) for r in by_address}
    if len(buyers) == 1:
        first = by_address[0]
        return {"state": "MATCHED", "method": "sender_address", "confidence": "MEDIUM", "company": first["company"],
                "experiment_id": first["experiment_id"], "campaign_id": first["campaign_id"], "person_id": first["person_id"],
                "note": "not in a governed thread; the sender address received exactly one buyer's governed send"}
    if len(buyers) > 1:
        return {"state": "AMBIGUOUS", "note": f"the sender address received governed sends for {len(buyers)} buyers"}
    same_domain = con.execute("SELECT COUNT(DISTINCT company) FROM outbound_messages WHERE recipient LIKE ?",
                              (f"%@{_domain(message['sender'])}",)).fetchone()[0]
    return {"state": "UNMATCHED", "note": (f"only the domain matches ({same_domain} governed buyer(s)); a domain alone "
                                           "never identifies a buyer") if same_domain else "no governed lineage"}


def _proposals(con, db_path: str, message: dict, kind: str, match: dict, new_text: str) -> list[dict]:
    # Automated mail is never a buyer reply, and a bounce of an ungoverned send is nothing to review.
    if kind in ("OUT_OF_OFFICE", "AUTOMATED") or (kind == "BOUNCE" and match["state"] != "MATCHED"):
        return []
    if match["state"] != "MATCHED":
        return [{"item": "identity", "proposed": False,
                 "reason": f"{match['state']}: {match['note']}. Verify the buyer and record by hand, or reject."}]
    if kind == "BOUNCE":
        recorded = any(e["event_type"] == "message_bounced" and entity(e) == match["company"].lower()
                       and e["experiment_id"] == match["experiment_id"] for e in effective_events(db_path))
        return [] if recorded else [{"item": "bounce", "type": "message_bounced", "proposed": True,
                                     "reason": "delivery failure in a governed thread"}]
    if kind == "UNSUBSCRIBE":
        return [{"item": "suppress", "type": "suppression", "proposed": True, "reason": "the sender asked not to be contacted"}]
    words = re.findall(r"[A-Za-z']+", new_text)
    acknowledgement = len(words) <= 5 and bool(words) and words[0].lower() in ACKNOWLEDGEMENT_WORDS
    items = [{"item": "event", "type": "reply_received", "proposed": True, "reason": "a person replied to governed outreach"}]
    cue = next((name for name, pattern in MEANINGFUL_CUES if pattern.search(new_text)), None)
    if acknowledgement or not cue:
        reason = ("an acknowledgement" if acknowledgement else
                  "information requested: whether this is meaningful needs human judgement" if INFORMATION_REQUEST.search(new_text)
                  else "no discussion, request or problem cue")
        items.append({"item": "meaningful", "type": "reply_meaningful", "proposed": False, "reason": reason})
    else:
        items.append({"item": "meaningful", "type": "reply_meaningful", "proposed": True,
                      "reason": f"{cue} — human approval required"})
    if acknowledgement:
        return items
    if message.get("body_is_snippet"):
        items.append({"item": "evidence", "proposed": False, "reason": "only a snippet was retrieved: fetch the full "
                      "message before any evidence can be proposed"})
        return items
    seen = {e["text"] for row in con.execute("SELECT proposals_json FROM reply_candidates WHERE source = ? AND "
                                             "source_thread_id = ? AND source_record_id != ?",
                                             (message["source"], message["source_thread_id"], message["source_record_id"]))
            for e in json.loads(row["proposals_json"]) if e["item"].startswith("E")}
    n = 0
    for clause in clauses(new_text):
        if clause in seen:
            continue  # the same words in an earlier message of this thread are one observation, not two
        for category, pattern in EVIDENCE_RULES:
            if pattern.search(clause):
                n += 1
                items.append({"item": f"E{n}", "category": category, "text": clause, "proposed": True,
                              "reason": f"wording matches the {category} rule; a person decides"})
    return items


def candidate_id_for(source: str, source_record_id: str) -> str:
    return "RC-" + hashlib.sha256(f"{source}\x1f{source_record_id}".encode()).hexdigest()[:12]


def capture(db_path: str, messages: Iterable[dict], *, mailbox: str) -> dict:
    """Turn retrieved messages into candidates. Writes nothing but candidates; a message already
    captured — pending, approved or rejected — is never proposed again."""
    init_db(db_path)
    mailbox = _address(mailbox)
    if not mailbox:
        raise ReplyCaptureError("mailbox_required", "name the mailbox the outreach was sent from")
    counts: Counter = Counter()
    for message in sorted(messages, key=lambda m: (m["occurred_at"], m["source_record_id"])):
        if message["sender"] == mailbox or "SENT" in message.get("labels", []):
            counts["own_messages"] += 1
            continue
        with connect(db_path) as con:
            if con.execute("SELECT 1 FROM reply_candidates WHERE source = ? AND source_record_id = ?",
                           (message["source"], message["source_record_id"])).fetchone():
                counts["already_captured"] += 1
                continue
            new_text = strip_quoted(message["body"])
            kind = _kind(message, new_text)
            match = _match(con, message, kind)
            proposals = _proposals(con, db_path, message, kind, match, new_text)
            candidate_id = candidate_id_for(message["source"], message["source_record_id"])
            con.execute(
                """INSERT INTO reply_candidates(candidate_id, source, source_record_id, source_thread_id, sender, subject,
                     occurred_at, body, kind, match_state, match_method, match_confidence, company, person_id,
                     experiment_id, campaign_id, proposals_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (candidate_id, message["source"], message["source_record_id"], message["source_thread_id"], message["sender"],
                 message["subject"], message["occurred_at"], new_text, kind, match["state"], match.get("method", ""),
                 match.get("confidence", ""), match.get("company", ""), match.get("person_id", ""),
                 match.get("experiment_id", ""), match.get("campaign_id", ""), json.dumps(proposals)))
        counts[f"{kind.lower()}_{match['state'].lower()}"] += 1
    return dict(counts)


# --- governed reply check -----------------------------------------------------------------

CANONICAL_TABLES = ("funnel_events", "evidence", "commercial_evidence", "suppression")


def _canonical_counts(db_path: str) -> dict[str, int]:
    with connect(db_path) as con:
        return {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in CANONICAL_TABLES}


def _lineage(db_path: str, experiment_id: str) -> tuple[list[dict], set[str]]:
    init_db(db_path)
    with connect(db_path) as con:
        rows = [dict(r) for r in con.execute("SELECT * FROM outbound_messages WHERE experiment_id = ? ORDER BY sent_at",
                                             (experiment_id,))]
        foreign = {r["thread_id"] for r in con.execute("SELECT thread_id FROM outbound_messages WHERE experiment_id != ?",
                                                       (experiment_id,))}
    if not rows:
        raise ReplyCaptureError("no_linked_sends", f"no governed outbound message is linked for {experiment_id}")
    return rows, foreign


def check_plan(db_path: str, experiment_id: str, *, since: str = "", until: str = "") -> dict:
    """The bounded retrieval for one experiment, derived only from its recorded outbound lineage.
    The Gmail connector runs these; nothing here reaches the mailbox."""
    rows, _ = _lineage(db_path, experiment_id)
    after = (since or rows[0]["sent_at"][:10]).replace("-", "/")
    before = f" before:{until.replace('-', '/')}" if until else ""
    recipients = sorted({r["recipient"] for r in rows})
    return {
        "experiment_id": experiment_id, "governed_threads": sorted({r["thread_id"] for r in rows}),
        "recipients": len(recipients),
        "searches": [
            {"purpose": "replies from governed recipients, including new threads", "include_trash": True,
             "query": f"in:anywhere after:{after}{before} -in:sent (" + " OR ".join(f"from:{a}" for a in recipients) + ")"},
            {"purpose": "governed threads with every message in them, bounces included", "include_trash": True,
             "query": f"in:sent after:{after}{before} (" + " OR ".join(f"to:{a}" for a in recipients) + ")"},
        ],
        "then": "fetch the full body (get_message, PLAIN_TEXT) of any inbound message that only has a snippet, "
                "save everything as one JSON payload, and run: age replies check PAYLOAD --experiment "
                f"{experiment_id} --mailbox <sending address>",
    }


def check(db_path: str, experiment_id: str, payload, *, mailbox: str, since: str = "", until: str = "") -> dict:
    """Capture review candidates for one experiment's governed outreach only. Out-of-scope mail is
    dropped, an inbound message known only by its snippet is held back until its body is fetched,
    and the run is refused if anything canonical changes: a check writes candidates, never facts."""
    rows, foreign = _lineage(db_path, experiment_id)
    threads, recipients = {r["thread_id"] for r in rows}, {r["recipient"] for r in rows}
    start, mailbox = since or rows[0]["sent_at"][:10], _address(mailbox)
    in_scope, held, out_of_scope, own = [], [], 0, 0
    for message in gmail_messages(payload):
        day = message["occurred_at"][:10]
        governed = message["source_thread_id"] in threads or (
            message["sender"] in recipients and message["source_thread_id"] not in foreign)
        if not governed or day < start or (until and day > until):
            out_of_scope += 1
            continue
        if message["sender"] == mailbox or "SENT" in message["labels"]:
            own += 1
            continue
        if message["body_is_snippet"] and not BOUNCE_SENDER.match(message["sender"]):
            held.append(message["source_record_id"])  # captured once, a snippet could never be read in full
            continue
        in_scope.append(message)
    before = _canonical_counts(db_path)
    counts = capture(db_path, in_scope, mailbox=mailbox)
    writes = {t: _canonical_counts(db_path)[t] - n for t, n in before.items()}
    if any(writes.values()):
        raise ReplyCaptureError("canonical_write_during_check", f"a check must not change canonical stores: {writes}")
    with connect(db_path) as con:
        ledger = [dict(r) for r in con.execute("SELECT candidate_id, kind, match_state FROM reply_candidates "
                                               f"WHERE source_thread_id IN ({','.join('?' * len(threads))}) "
                                               f"OR sender IN ({','.join('?' * len(recipients))})",
                                               (*threads, *recipients))]
    new = {k: v for k, v in counts.items() if k not in ("already_captured", "own_messages")}
    return {
        "experiment_id": experiment_id, "window": [start, until or "open"],
        "threads_checked": len(threads), "recipients_checked": len(recipients),
        "out_of_scope_dropped": out_of_scope, "own_messages": own,
        "inbound_found": len(in_scope) + len(held), "already_processed": counts.get("already_captured", 0),
        "needs_full_body": held, "new_candidates": new,
        "automated": sum(v for k, v in new.items() if k.startswith(("automated", "out_of_office"))),
        "bounces": sum(v for k, v in new.items() if k.startswith("bounce")),
        "buyer_reply_candidates": sum(v for k, v in new.items() if k.startswith(("buyer_reply", "unsubscribe"))),
        "ambiguous_or_unmatched": sum(v for k, v in new.items() if not k.endswith("_matched")),
        "pending_review": sum(1 for c in (_candidate(db_path, r["candidate_id"]) for r in ledger) if c["pending"]),
        "real_buyer_replies": sum(1 for r in ledger if r["kind"] == "BUYER_REPLY" and r["match_state"] == "MATCHED"),
        "canonical_writes": sum(writes.values()),
    }


def render_check(s: dict) -> str:
    lines = [f"{s['experiment_id']} REPLY CHECK  [review candidates only · window {s['window'][0]}..{s['window'][1]}]",
             f"Threads checked: {s['threads_checked']} (recipients {s['recipients_checked']})",
             f"Out-of-scope mail dropped: {s['out_of_scope_dropped']}",
             f"Inbound messages found: {s['inbound_found']}",
             f"Already processed: {s['already_processed']}",
             f"Automated: {s['automated']}", f"Bounces: {s['bounces']}",
             f"Buyer reply candidates: {s['buyer_reply_candidates']}",
             f"Ambiguous/unmatched: {s['ambiguous_or_unmatched']}",
             f"Pending human review: {s['pending_review']}",
             f"Canonical writes by this check: {s['canonical_writes']}"]
    if s["needs_full_body"]:
        lines.append(f"Held back, snippet only (fetch the full body, then re-run): {len(s['needs_full_body'])}")
    lines.append(f"REAL BUYER REPLIES FOUND: {s['real_buyer_replies']}")
    return "\n".join(lines)


# --- review and approval ------------------------------------------------------------------

def candidate(db_path: str, candidate_id: str) -> dict:
    return _candidate(db_path, candidate_id)


def _candidate(db_path: str, candidate_id: str) -> dict:
    with connect(db_path) as con:
        row = con.execute("SELECT * FROM reply_candidates WHERE candidate_id = ?", (candidate_id,)).fetchone()
        if row is None:
            raise ReplyCaptureError("not_found", f"no reply candidate {candidate_id}")
        decisions = {r["item"]: dict(r) for r in con.execute("SELECT * FROM reply_decisions WHERE candidate_id = ?",
                                                             (candidate_id,))}
    candidate = dict(row)
    candidate["proposals"] = json.loads(candidate.pop("proposals_json"))
    candidate["decisions"] = decisions
    # Undecided: anything a person may still approve or reject. Pending: what awaits a decision —
    # the rules' proposals, plus an unresolved identity. A non-proposed item (a reply the rules did
    # not think meaningful) can still be approved on human judgement, but it does not nag.
    candidate["undecided"] = [p["item"] for p in candidate["proposals"]
                              if p["item"] not in decisions and p["item"] != "evidence"]
    candidate["pending"] = [p["item"] for p in candidate["proposals"] if p["item"] in candidate["undecided"]
                            and (p.get("proposed") or p["item"] == "identity")]
    return candidate


def review(db_path: str) -> dict:
    init_db(db_path)
    with connect(db_path) as con:
        ids = [r["candidate_id"] for r in con.execute("SELECT candidate_id FROM reply_candidates ORDER BY occurred_at")]
        kinds = Counter(f"{r['kind']}/{r['match_state']}" for r in con.execute("SELECT kind, match_state FROM reply_candidates"))
    candidates = [_candidate(db_path, i) for i in ids]
    return {"pending": [c for c in candidates if c["pending"]], "captured": len(candidates), "by_kind": dict(kinds)}


def pending_count(db_path: str) -> int:
    return len(review(db_path)["pending"])


def _decide(con, candidate_id: str, item: str, decision: str, decided_by: str, detail: dict, result_ref: str = "") -> None:
    con.execute("""INSERT INTO reply_decisions(candidate_id, item, decision, detail_json, result_ref, decided_by)
                   VALUES (?, ?, ?, ?, ?, ?)""", (candidate_id, item, decision, json.dumps(detail, sort_keys=True),
                                                  result_ref, decided_by))


def approve(db_path: str, candidate_id: str, *, items: Iterable[str] | None = None, categories: dict | None = None,
            texts: dict | None = None, decided_by: str = "founder") -> dict:
    """Approve chosen items, or every item the rules proposed. Evidence and a meaningful reply need
    the reply event approved first. Edits may change a category, or narrow a citation to an exact
    substring of the buyer's own words; they never add words."""
    candidate = _candidate(db_path, candidate_id)
    categories, texts = categories or {}, texts or {}
    by_item = {p["item"]: p for p in candidate["proposals"]}
    chosen = list(items) if items else [p["item"] for p in candidate["proposals"] if p.get("proposed") and p["item"] in candidate["pending"]]
    for item in chosen:
        if item not in by_item or item == "evidence":
            raise ReplyCaptureError("unknown_item", f"{candidate_id} has no item {item!r}")
        if item in candidate["decisions"]:
            raise ReplyCaptureError("already_decided", f"{item} was already {candidate['decisions'][item]['decision']}")
        if item == "identity":
            raise ReplyCaptureError("identity_unresolved", "an unmatched or ambiguous reply cannot be approved; verify "
                                    "the buyer and record it by hand, or reject it")
    event_approved = "event" in chosen or candidate["decisions"].get("event", {}).get("decision") == "APPROVED"
    if any(i == "meaningful" or i.startswith("E") for i in chosen) and not event_approved:
        raise ReplyCaptureError("event_first", "approve the reply event before a meaningful reply or its evidence")
    edited = {}
    for item in (i for i in chosen if i.startswith("E")):
        text = texts.get(item, by_item[item]["text"])
        category = categories.get(item, by_item[item]["category"])
        if text not in candidate["body"]:
            raise ReplyCaptureError("text_not_in_reply", f"{item}: an edit may only narrow the citation to the buyer's own words")
        if category not in CATEGORIES:
            raise ReplyCaptureError("unknown_category", f"{item}: {category!r} is not a buyer-truth category")
        edited[item] = {"text": text, "category": category}

    base = {"company": candidate["company"], "person_id": candidate["person_id"], "experiment_id": candidate["experiment_id"],
            "campaign_id": candidate["campaign_id"], "channel": "email", "source": candidate["source"],
            "source_record_id": candidate["source_record_id"], "occurred_at": candidate["occurred_at"],
            "provenance": "platform_export",
            "metadata": {"source_thread_id": candidate["source_thread_id"], "candidate_id": candidate_id,
                         "match_method": candidate["match_method"], "approved_by": decided_by}}
    # The governed send this message answers. When it is verifiable it must already be in the funnel:
    # a reply or a bounce never enters without its upstream exposure.
    if any(i in ("event", "meaningful", "bounce") or i.startswith("E") for i in chosen) and candidate["source_thread_id"]:
        with connect(db_path) as con:
            sends = [r["message_id"] for r in con.execute(
                "SELECT message_id FROM outbound_messages WHERE source = ? AND thread_id = ? AND sent_at <= ? "
                "ORDER BY sent_at", (candidate["source"], candidate["source_thread_id"], candidate["occurred_at"]))]
        if sends:
            upstream = event_id_for(candidate["source"], sends[-1], "message_sent")
            if upstream not in {e["event_id"] for e in effective_events(db_path, include_synthetic=True)}:
                raise ReplyCaptureError("upstream_send_missing", "the governed send this answers is verifiable but not "
                                        f"recorded: run `age replies import-sends {candidate['experiment_id']}` first")
            base["metadata"]["answers_send_event_id"] = upstream
    results: dict[str, str] = {}
    event_id = candidate["decisions"].get("event", {}).get("result_ref", "")
    for item in sorted(chosen, key=lambda i: (i != "event", i)):
        try:
            if item in ("event", "meaningful", "bounce"):
                event_type = by_item[item]["type"]
                results[item] = record_event(db_path, {**base, "event_type": event_type})["event_id"]
                event_id = results[item] if item == "event" else event_id
            elif item == "suppress":
                with connect(db_path) as con:
                    con.execute("INSERT OR IGNORE INTO suppression(identity, reason) VALUES (?, ?)",
                                (candidate["sender"], f"asked not to be contacted ({candidate['source']} {candidate['source_record_id']})"))
                results[item] = candidate["sender"]
        except EventError as exc:
            raise ReplyCaptureError(exc.code, str(exc)) from exc
    grouped: dict[str, list[str]] = {}
    for item, edit in edited.items():
        grouped.setdefault(edit["text"], []).append(edit["category"])
    for text, cats in grouped.items():
        try:
            recorded = record_commercial_evidence(
                db_path, statement=text, categories=cats, source=candidate["source"],
                source_record_id=candidate["source_record_id"], occurred_at=candidate["occurred_at"],
                provenance="platform_export", company=candidate["company"], person_id=candidate["person_id"],
                source_event_id=event_id, experiment_id=candidate["experiment_id"], campaign_id=candidate["campaign_id"])
        except BuyerTruthError as exc:
            raise ReplyCaptureError(exc.code, str(exc)) from exc
        for item, edit in edited.items():
            if edit["text"] == text:
                results[item] = recorded["evidence_id"]
    with connect(db_path) as con:
        for item in chosen:
            _decide(con, candidate_id, item, "APPROVED", decided_by, edited.get(item, {}), results.get(item, ""))
    return {"candidate_id": candidate_id, "approved": results}


def reject(db_path: str, candidate_id: str, *, items: Iterable[str] | None = None, reason: str,
           decided_by: str = "founder") -> dict:
    """Reject chosen items, or everything still pending. Nothing is written to events or evidence."""
    if not reason.strip():
        raise ReplyCaptureError("reason_required", "a rejection needs its reason")
    candidate = _candidate(db_path, candidate_id)
    chosen = list(items) if items else list(candidate["undecided"])
    for item in chosen:
        if item not in candidate["undecided"]:
            raise ReplyCaptureError("not_pending", f"{item} is not an undecided item of {candidate_id}")
    with connect(db_path) as con:
        for item in chosen:
            _decide(con, candidate_id, item, "REJECTED", decided_by, {"reason": reason.strip()})
    return {"candidate_id": candidate_id, "rejected": chosen}


def render_review(result: dict) -> str:
    lines = [f"REPLY REVIEW  [PROPOSALS — nothing is recorded until approved]  captured {result['captured']} · "
             f"pending {len(result['pending'])} · {result['by_kind']}"]
    for c in result["pending"]:
        lines += ["", f"REPLY CANDIDATE {c['candidate_id']}  [{c['kind']} · {c['match_state']}"
                      + (f" · {c['match_method']} {c['match_confidence']}" if c["match_method"] else "") + "]",
                  f"Buyer: {c['person_id'] or 'no person id recorded'} · sender {c['sender']}",
                  f"Company: {c['company'] or 'not identified'}",
                  f"Experiment: {c['experiment_id'] or '-'}", f"Campaign: {c['campaign_id'] or '-'}",
                  f"Received: {c['occurred_at']}", f"Source: {c['source']} message {c['source_record_id']}",
                  "Reply:", f"  \"{c['body'][:600]}\""]
        for p in c["proposals"]:
            state = c["decisions"].get(p["item"], {}).get("decision",
                                                          "PENDING" if p["item"] in c["pending"] else "OPTIONAL — your judgement")
            if p["item"] == "event":
                lines.append(f"PROPOSED EVENT  reply_received  [{state}]")
            elif p["item"] == "meaningful":
                lines.append(f"MEANINGFUL REPLY  {'PROPOSED' if p['proposed'] else 'NOT PROPOSED'} — {p['reason']}  [{state}]")
            elif p["item"].startswith("E"):
                lines.append(f"{p['item']}. Category: {p['category']}  [{state}]\n    Evidence: \"{p['text']}\"")
            else:
                lines.append(f"{p['item'].upper()}  {p['reason']}  [{state}]")
        approvable = [i for i in c["pending"] if i != "identity"]
        lines.append((f"Actions: age replies approve {c['candidate_id']} --items {','.join(approvable)} · " if approvable else "Actions: ")
                     + f"age replies reject {c['candidate_id']} --items {','.join(c['pending'])} --reason ...")
    return "\n".join(lines)
