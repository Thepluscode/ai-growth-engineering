"""Buyer truth: what a buyer actually said, linked to the buyer, the commercial event and the money.

    OBSERVED     evidence.statement — verbatim, or backed by a named source record
    DERIVED      commercial_evidence.category — recorded by a person against that statement
    INTERPRETED  evidence_interpretations.theme — appended, and allowed to change later

The observation is an ordinary `evidence` row and is never rewritten (a trigger refuses it once
linked). No model classifies anything here. A reply or a meeting is a funnel event; it becomes
evidence only through specific statements recorded against it, each with its own source record.
"""
from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from typing import Iterable

from .funnel_events import PROVENANCES, EventError, _occurred_at, effective_events
from .models import Evidence, EvidenceKind
from .registry import add_evidence
from .revenue_loop import entity, totals
from .storage import connect, init_db

CATEGORIES = (
    "PROBLEM_STATED", "PAIN_CONFIRMED", "DESIRED_OUTCOME", "OBJECTION", "BUYING_CRITERION",
    "URGENCY_SIGNAL", "BUDGET_SIGNAL", "AUTHORITY_SIGNAL", "ALTERNATIVE_MENTIONED",
    "REASON_FOR_INTEREST", "REASON_FOR_REJECTION", "REASON_FOR_PURCHASE",
    "WILLINGNESS_TO_PAY_STATED", "PROPOSAL_REQUESTED",
)
# Events that can carry the buyer's own words. A send or an invitation carries only ThePlus's.
CONVERSATION_EVENTS = frozenset({
    "reply_received", "reply_meaningful", "lead_created", "lead_qualified", "lead_disqualified",
    "meeting_booked", "meeting_held", "proposal_sent", "proposal_accepted", "proposal_rejected",
    "customer_won", "customer_lost", "payment_received",
})
PURCHASE_EVENTS = frozenset({"proposal_accepted", "customer_won", "payment_received"})
PROBLEM_CATEGORIES = frozenset({"PROBLEM_STATED", "PAIN_CONFIRMED"})
# Shown as NOT OBSERVED on a customer when absent, because their absence is itself informative.
KEY_CATEGORIES = ("PROBLEM_STATED", "OBJECTION", "BUYING_CRITERION", "REASON_FOR_PURCHASE")
# Willingness to pay, strongest first: behaviour outranks words, and the rungs are never collapsed.
WTP_LADDER = (
    ("payment_received", ("payment_received",), ()),
    ("signed_commercial_action", ("proposal_accepted", "customer_won"), ()),
    ("proposal_requested", (), ("PROPOSAL_REQUESTED",)),
    ("budget_discussed", (), ("BUDGET_SIGNAL",)),
    ("willingness_to_pay_stated", (), ("WILLINGNESS_TO_PAY_STATED",)),
    ("positive_interest", (), ("REASON_FOR_INTEREST",)),
)
FORWARD_STAGES = (
    ("qualified_conversations", ("reply_meaningful", "lead_qualified")),
    ("meetings", ("meeting_booked", "meeting_held")),
    ("proposals", ("proposal_sent",)),
    ("customers", ("customer_won", "payment_received")),
)
# ponytail: a word count cannot tell pain from politeness. It only refuses acknowledgements such
# as "Thanks."; the person recording still asserts the category against the source record.
MIN_OBSERVATION_WORDS = 3
SEGMENT_MIN_ORGANISATIONS = 3
OBJECTION_MIN_ORGANISATIONS = 2
THEME = re.compile(r"^[a-z0-9][a-z0-9-]{1,79}$")


class BuyerTruthError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _digest(*parts: str) -> str:
    return hashlib.sha256("\x1f".join(parts).encode()).hexdigest()[:16]


def record_commercial_evidence(db_path: str, *, statement: str, categories: Iterable[str], source: str,
                               source_record_id: str, occurred_at: str, provenance: str = "operator_recorded",
                               company: str = "", person_id: str = "", source_event_id: str = "",
                               experiment_id: str = "", campaign_id: str = "", offer_id: str = "",
                               verbatim: bool = True) -> dict:
    """Record one observed statement and the categories it establishes. Nothing is inferred: an
    unsourced, unattributed or acknowledgement-only statement is refused, not softened."""
    init_db(db_path)
    statement = statement.strip()
    categories = tuple(dict.fromkeys(c.strip().upper() for c in categories))
    if not categories:
        raise BuyerTruthError("category_required", "a statement that establishes nothing is not commercial "
                              "evidence; the funnel event alone records that the buyer replied")
    unknown = [c for c in categories if c not in CATEGORIES]
    if unknown:
        raise BuyerTruthError("unknown_category", f"unknown categories {unknown}")
    if len(statement.split()) < MIN_OBSERVATION_WORDS:
        raise BuyerTruthError("not_an_observation",
                              f"{statement!r} is an acknowledgement, not evidence of a problem, budget or intent")
    source, source_record_id = source.strip(), source_record_id.strip()
    if not source or not source_record_id:
        raise BuyerTruthError("missing_source", "commercial evidence needs the source record it was observed in")
    if provenance not in PROVENANCES:
        raise BuyerTruthError("invalid_provenance", f"provenance must be one of {PROVENANCES}")
    try:
        occurred_at = _occurred_at(occurred_at)
    except EventError as exc:
        raise BuyerTruthError(exc.code, str(exc)) from exc
    company, person_id = company.strip(), person_id.strip()
    if not (company or person_id):
        raise BuyerTruthError("buyer_required", "evidence must name the buyer's company or person id")
    buyer = (company or person_id).lower()
    events = effective_events(db_path, include_synthetic=True)
    lineage = {"experiment_id": experiment_id.strip(), "campaign_id": campaign_id.strip(), "offer_id": offer_id.strip()}
    if source_event_id:
        event = next((e for e in events if e["event_id"] == source_event_id), None)
        if event is None:
            raise BuyerTruthError("event_not_found", f"{source_event_id} is not an effective funnel event")
        if event["event_type"] not in CONVERSATION_EVENTS:
            raise BuyerTruthError("not_a_conversation", f"{event['event_type']} carries no words from the buyer")
        if entity(event) != buyer:
            raise BuyerTruthError("buyer_mismatch", f"{source_event_id} is about {entity(event)!r}, not {buyer!r}")
        for key in ("experiment_id", "campaign_id"):
            if lineage[key] and event[key] and lineage[key] != event[key]:
                raise BuyerTruthError("lineage_conflict", f"{key} {lineage[key]!r} contradicts the event's {event[key]!r}")
            lineage[key] = lineage[key] or event[key]
    if "REASON_FOR_PURCHASE" in categories and not any(
            e["event_type"] in PURCHASE_EVENTS and entity(e) == buyer for e in events):
        raise BuyerTruthError("no_purchase", "a reason for purchase needs a recorded purchase by this buyer; "
                              "before that it is REASON_FOR_INTEREST")
    if lineage["campaign_id"] and not lineage["offer_id"]:
        with connect(db_path) as con:
            row = con.execute("SELECT offer_id FROM campaigns WHERE campaign_id = ?", (lineage["campaign_id"],)).fetchone()
        lineage["offer_id"] = row["offer_id"] if row else ""

    evidence_id = f"EV-CE-{_digest(source, source_record_id, statement)}"
    with connect(db_path) as con:
        exists = con.execute("SELECT 1 FROM evidence WHERE evidence_id = ?", (evidence_id,)).fetchone()
    if not exists:
        # Confidence here is how exactly the record holds the buyer's words: verbatim, or a
        # source-backed paraphrase at the claim gate's floor.
        add_evidence(db_path, Evidence(
            evidence_id=evidence_id, kind=EvidenceKind.CUSTOMER_QUOTE if verbatim else EvidenceKind.CRM,
            statement=statement, source=f"{source}:{source_record_id}", confidence=1.0 if verbatim else 0.5,
            observed=True, observed_at=occurred_at,
            metadata={"source": source, "source_record_id": source_record_id, "source_event_id": source_event_id,
                      "provenance": provenance, "verbatim": verbatim}))
    link_ids, inserted = [], []
    with connect(db_path) as con:
        for category in categories:
            link_id = f"CE-{_digest(evidence_id, category)}"
            link_ids.append(link_id)
            if con.execute("SELECT 1 FROM commercial_evidence WHERE link_id = ?", (link_id,)).fetchone():
                continue
            con.execute(
                """INSERT INTO commercial_evidence(link_id, evidence_id, category, person_id, company, occurred_at,
                     source, source_record_id, source_event_id, experiment_id, campaign_id, offer_id, provenance)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (link_id, evidence_id, category, person_id, company, occurred_at, source, source_record_id,
                 source_event_id or None, lineage["experiment_id"], lineage["campaign_id"], lineage["offer_id"],
                 provenance))
            inserted.append(link_id)
    return {"evidence_id": evidence_id, "link_ids": link_ids, "inserted": inserted}


def interpret(db_path: str, link_id: str, *, theme: str, interpretation: str, confidence: float,
              interpreted_by: str) -> dict:
    """Append a reading of one linked observation. The observation is untouched; the newest reading wins."""
    init_db(db_path)
    theme = theme.strip()
    if not THEME.match(theme):
        raise BuyerTruthError("invalid_theme", "a theme is a lowercase slug, e.g. agent-decision-traceability")
    if not interpretation.strip() or not interpreted_by.strip():
        raise BuyerTruthError("interpretation_required", "an interpretation needs its text and who made it")
    if isinstance(confidence, bool) or not 0 <= float(confidence) <= 1:
        raise BuyerTruthError("invalid_confidence", "confidence must be between 0 and 1")
    interpretation_id = f"INT-{_digest(link_id, theme, interpretation.strip(), interpreted_by.strip(), str(confidence))}"
    with connect(db_path) as con:
        if con.execute("SELECT 1 FROM commercial_evidence WHERE link_id = ?", (link_id,)).fetchone() is None:
            raise BuyerTruthError("link_not_found", f"no commercial evidence {link_id}")
        if con.execute("SELECT 1 FROM evidence_interpretations WHERE interpretation_id = ?",
                       (interpretation_id,)).fetchone() is None:
            con.execute(
                """INSERT INTO evidence_interpretations(interpretation_id, link_id, theme, interpretation,
                     confidence, interpreted_by) VALUES (?, ?, ?, ?, ?, ?)""",
                (interpretation_id, link_id, theme, interpretation.strip(), float(confidence), interpreted_by.strip()))
    return {"interpretation_id": interpretation_id, "link_id": link_id, "theme": theme}


def buyer_evidence(db_path: str, *, include_synthetic: bool = False) -> list[dict]:
    """Every linked observation with its current interpretation. Synthetic fixtures are excluded
    unless asked for, so a demonstration can never read as customer truth."""
    init_db(db_path)
    with connect(db_path) as con:
        rows = [dict(r) for r in con.execute(
            """SELECT ce.*, e.statement AS observation, e.kind AS evidence_kind,
                      EXISTS(SELECT 1 FROM funnel_events c WHERE c.corrects_event_id = ce.source_event_id)
                        AS source_event_voided
               FROM commercial_evidence ce JOIN evidence e ON e.evidence_id = ce.evidence_id
               WHERE (? OR ce.provenance != 'synthetic_fixture')
               ORDER BY ce.occurred_at, ce.link_id""", (int(include_synthetic),))]
        history: dict[str, list[dict]] = defaultdict(list)
        for row in con.execute("SELECT * FROM evidence_interpretations ORDER BY recorded_at, rowid"):
            history[row["link_id"]].append(dict(row))
    for row in rows:
        past = history.get(row["link_id"], [])
        row.update(buyer=(row["company"] or row["person_id"]).lower(),
                   observed_as="verbatim" if row.pop("evidence_kind") == EvidenceKind.CUSTOMER_QUOTE.value
                   else "source_backed",
                   source_event_voided=bool(row["source_event_voided"]),
                   interpretation=past[-1] if past else None,
                   interpretation_status="interpreted" if past else "uninterpreted",
                   interpretation_history=len(past))
    return rows


def scope(items: Iterable[dict]) -> dict:
    """How far a theme may be generalised, counted from who said it. One buyer is buyer truth."""
    items = list(items)
    people = {i["person_id"] or i["buyer"] for i in items}
    organisations = {i["company"].strip().lower() for i in items if i["company"].strip()}
    orgs = len(organisations)
    if orgs >= SEGMENT_MIN_ORGANISATIONS:
        level = "SEGMENT_CANDIDATE"
    elif orgs == 2:
        level = "CROSS_ORGANISATION"
    elif len(people) >= 2 and orgs == 1:
        level = "ORGANISATION"
    else:
        level = "BUYER"
    return {"level": level, "organisations": orgs, "people": len(people),
            "confidence": "LOW" if orgs < SEGMENT_MIN_ORGANISATIONS else "MEDIUM" if orgs < 10 else "HIGH",
            "reason": "one buyer" if level == "BUYER" else f"{orgs} organisation(s), {len(people)} people",
            # Even a segment candidate is a candidate: a published claim still goes through the claim gate.
            "generalisable": level == "SEGMENT_CANDIDATE"}


def willingness_to_pay(events: list[dict], evidence: list[dict], buyer: str) -> dict:
    rungs = []
    for name, event_types, categories in WTP_LADDER:
        ids = ([e["event_id"] for e in events if e["event_type"] in event_types and entity(e) == buyer]
               + [i["evidence_id"] for i in evidence if i["category"] in categories and i["buyer"] == buyer])
        rungs.append({"rung": name, "observed": bool(ids), "ids": ids})
    return {"strongest": next((r["rung"] for r in rungs if r["observed"]), None), "rungs": rungs}


def _themes(items: Iterable[dict], categories: frozenset[str]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for item in items:
        if item["category"] in categories and item["interpretation"]:
            grouped[item["interpretation"]["theme"]].append(item)
    return grouped


def buyer_truth(evidence: list[dict], events: list[dict], buyer: str) -> dict:
    """What this buyer said, by category, with the evidence id behind each line."""
    mine = [i for i in evidence if i["buyer"] == buyer]
    observed: dict[str, list[dict]] = defaultdict(list)
    for i in mine:
        observed[i["category"]].append({
            **{k: i[k] for k in ("observation", "evidence_id", "link_id", "occurred_at", "source",
                                 "source_record_id", "source_event_id", "observed_as", "interpretation_status")},
            "interpretation": i["interpretation"] and {k: i["interpretation"][k] for k in
                                                       ("theme", "interpretation", "confidence", "interpreted_by")},
        })
    everyone = _themes(evidence, PROBLEM_CATEGORIES)
    return {
        "observed": dict(observed),
        "not_observed": [c for c in KEY_CATEGORIES if c not in observed],
        "willingness_to_pay": willingness_to_pay(events, evidence, buyer),
        "interpreted_problems": [
            {"theme": theme, "scope": scope(everyone[theme]),
             "evidence_ids": sorted({i["evidence_id"] for i in items}),
             "interpretations": sorted({i["interpretation"]["interpretation"] for i in items})}
            for theme, items in sorted(_themes(mine, PROBLEM_CATEGORIES).items())],
    }


def problem_revenue(evidence: list[dict], events: list[dict]) -> list[dict]:
    """Problem -> buyers who stated it -> how far those buyers went -> money they actually paid."""
    views = []
    for theme, items in _themes(evidence, PROBLEM_CATEGORIES).items():
        buyers = {i["buyer"] for i in items}
        view = {"theme": theme, "scope": scope(items), "buyers_stating": len(buyers),
                "evidence_ids": sorted({i["evidence_id"] for i in items})}
        for name, types in FORWARD_STAGES:
            view[name] = len({entity(e) for e in events if e["event_type"] in types and entity(e) in buyers})
        view["observed_revenue_pence"] = totals(
            [e for e in events if entity(e) in buyers and e["event_type"] in ("payment_received", "refund")])["revenue_pence"]
        views.append(view)
    return sorted(views, key=lambda v: (-v["observed_revenue_pence"], -v["customers"], -v["proposals"],
                                        -v["meetings"], -v["scope"]["organisations"], v["theme"]))


def theme_counts(items: Iterable[dict], category: str) -> list[dict]:
    grouped = _themes(items, frozenset({category}))
    counts = [{"theme": theme, "organisations": scope(group)["organisations"], "buyers": len({i["buyer"] for i in group}),
               "evidence_ids": sorted({i["evidence_id"] for i in group})} for theme, group in grouped.items()]
    return sorted(counts, key=lambda c: (-c["organisations"], -c["buyers"], c["theme"]))


def stalled_objections(evidence: list[dict], events: list[dict]) -> list[dict]:
    """Objections raised by buyers who reached a proposal and did not buy, where enough independent
    organisations raised the same one to be more than one buyer's view."""
    proposed = {entity(e) for e in events if e["event_type"] == "proposal_sent"}
    bought = {entity(e) for e in events if e["event_type"] in PURCHASE_EVENTS}
    stalled = [i for i in evidence if i["buyer"] in proposed - bought]
    return [c for c in theme_counts(stalled, "OBJECTION") if c["organisations"] >= OBJECTION_MIN_ORGANISATIONS]


def truth_summary(evidence: list[dict], events: list[dict]) -> dict | None:
    """The status-page view. None when nothing has been observed, so empty categories never show."""
    if not evidence:
        return None
    summary: dict = {"observations": len({i["evidence_id"] for i in evidence}),
                     "uninterpreted": len({i["evidence_id"] for i in evidence if not i["interpretation"]})}
    problems = problem_revenue(evidence, events)
    if problems:
        summary["best_evidenced_problem"] = max(problems, key=lambda p: (p["scope"]["organisations"], p["buyers_stating"]))
        commercial = [p for p in problems if p["proposals"] or p["customers"]]
        if commercial:
            summary["strongest_commercial_problem"] = commercial[0]
    for key, category in (("common_objection", "OBJECTION"), ("buying_criterion", "BUYING_CRITERION")):
        counts = theme_counts(evidence, category)
        if counts:
            summary[key] = counts[0]
    strong, best = summary.get("strongest_commercial_problem"), summary.get("best_evidenced_problem")
    if strong and strong["customers"]:
        summary["current_uncertainty"] = (f"Whether a second buyer pays to solve {strong['theme']}." if strong["customers"] == 1
                                          else f"Whether {strong['theme']} keeps paying beyond {strong['customers']} customers.")
    elif strong:
        summary["current_uncertainty"] = f"Whether buyers with {strong['theme']} pay: {strong['proposals']} proposal(s), no customer yet."
    elif best:
        next_stage = "request proposals for" if best["meetings"] else "take meetings about"
        summary["current_uncertainty"] = f"Whether {best['theme']} is a problem buyers {next_stage}."
    else:
        summary["current_uncertainty"] = "Observations are linked, but none is interpreted to a problem theme yet."
    return summary
