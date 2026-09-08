"""EXP-ACQ-0003 execution: freeze a cohort, record access outcomes, return the verdict.

The invariant this module exists to enforce:

    NO DOWNSTREAM STATE WITHOUT ADMISSIBLE UPSTREAM LINEAGE

    candidate     is not  qualified
    identity      is not  access
    acceptance    is not  demand
    reply         is not  pain
    pain          is not  willingness to pay
    proposal      is not  revenue

Each stage is a separate table and a separate assertion. The failure this prevents has
already happened twice in this repository at two different depths: `qualified_prospects`
counted anything that was not disqualified, and 46 accounts carried a LinkedIn identity
while only 39 of them had ever been qualified. Both were validation manufactured by
omission rather than by evidence.

An invitation acceptance recorded here tests **access** and nothing else. It cannot reach
`outreach`, so it cannot increment replies, discovery, proposals or revenue.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Mapping

from .storage import connect, init_db


class ExecutionError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


TREATMENT = "standard_invitation_no_note"
OUTCOMES = ("not_submitted", "pending", "accepted", "withdrawn", "restricted", "undeliverable")

# Preregistered bands, expressed as counts against the frozen cohort so no rate has to be
# recomputed at decision time. 29 is the accepted-connection count the downstream message
# stage needs to reject KEEP at a true 10% reply rate.
ACCEPTS_FOR_DOWNSTREAM = 29
PIVOT_RATE_CEILING = 0.193


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, centre - half), min(1.0, centre + half))


def freeze_execution_cohort(db_path: str, cohort_id: str, *, frozen_at: str | None = None) -> dict:
    """Admit exactly the accounts with admissible upstream lineage, and freeze them.

    Admissible means: the prospect carries an explicit `qualified%` status AND has at
    least one LinkedIn identity. One invitation per account, per the protocol's admission
    rule 4 — a second director at the same company is a second touch, not a second
    observation — so the highest-confidence identity is the one frozen.
    """
    init_db(db_path)
    stamp = frozen_at or _utc_now()
    with connect(db_path) as con:
        if con.execute("SELECT 1 FROM execution_cohort WHERE cohort_id = ?", (cohort_id,)).fetchone():
            raise ExecutionError("cohort_frozen", f"{cohort_id} is already frozen and cannot be refrozen")
        rows = con.execute(
            """SELECT p.id AS prospect_id, p.company, p.status, p.evidence,
                      i.id AS identity_id, i.value, i.confidence, i.provider
               FROM prospects p
               JOIN prospect_identities i ON i.prospect_id = p.id
               WHERE i.identity_type = 'linkedin' AND p.status LIKE 'qualified%'
               ORDER BY p.id, i.confidence DESC, i.id"""
        ).fetchall()
        best: dict[int, Any] = {}
        for row in rows:
            best.setdefault(row["prospect_id"], row)
        for row in best.values():
            sourcing = "two_source" if row["confidence"] >= 0.8 else "single_source"
            ownership = ("SINGLE_DIRECTOR" if "SINGLE_DIRECTOR" in (row["evidence"] or "")
                         else "MULTI_DIRECTOR" if "MULTI_DIRECTOR" in (row["evidence"] or "")
                         else "UNKNOWN")
            con.execute(
                """INSERT INTO execution_cohort(
                     cohort_id, prospect_id, identity_id, identity_value, frozen_at,
                     identity_confidence, identity_sourcing, ownership_structure)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (cohort_id, row["prospect_id"], row["identity_id"], row["value"], stamp,
                 row["confidence"], sourcing, ownership),
            )
            con.execute(
                """INSERT INTO invitations(cohort_id, prospect_id, treatment, outcome)
                   VALUES (?, ?, ?, 'not_submitted')""",
                (cohort_id, row["prospect_id"], TREATMENT),
            )
    return cohort(db_path, cohort_id)


def cohort(db_path: str, cohort_id: str) -> dict:
    init_db(db_path)
    with connect(db_path) as con:
        rows = [dict(r) for r in con.execute(
            """SELECT c.*, p.company, p.status, v.outcome, v.submitted_at, v.accepted_at, v.note
               FROM execution_cohort c
               JOIN prospects p ON p.id = c.prospect_id
               JOIN invitations v ON v.cohort_id = c.cohort_id AND v.prospect_id = c.prospect_id
               WHERE c.cohort_id = ?
               ORDER BY p.company""", (cohort_id,))]
    return {"cohort_id": cohort_id, "size": len(rows), "members": rows}


def record_invitation(db_path: str, cohort_id: str, prospect_id: int, values: Mapping[str, Any]) -> dict:
    """Record what a person observed after submitting one invitation.

    Refuses any prospect outside the frozen cohort: an account cannot acquire an access
    outcome without having been admitted upstream.
    """
    init_db(db_path)
    outcome = str(values.get("outcome") or "").strip().lower()
    if outcome not in OUTCOMES:
        raise ExecutionError("invalid_outcome", f"outcome must be one of {', '.join(OUTCOMES)}")
    treatment = str(values.get("treatment") or TREATMENT)
    if treatment != TREATMENT:
        raise ExecutionError(
            "treatment_changed",
            "the invitation treatment is preregistered and frozen; a note-bearing invitation "
            "belongs to a different experiment")
    accepted_at = str(values.get("accepted_at") or "")
    if outcome == "accepted" and not accepted_at:
        raise ExecutionError("acceptance_needs_timestamp", "an acceptance must record when it happened")
    if outcome != "accepted" and accepted_at:
        raise ExecutionError("acceptance_timestamp_without_acceptance",
                             "only an accepted invitation may carry an acceptance timestamp")
    with connect(db_path) as con:
        member = con.execute(
            "SELECT 1 FROM execution_cohort WHERE cohort_id = ? AND prospect_id = ?",
            (cohort_id, prospect_id)).fetchone()
        if member is None:
            raise ExecutionError(
                "not_in_cohort",
                "prospect is not in the frozen cohort; an unadmitted account cannot record access")
        con.execute(
            """UPDATE invitations SET outcome = ?, submitted_at = ?, accepted_at = ?, note = ?
               WHERE cohort_id = ? AND prospect_id = ?""",
            (outcome, str(values.get("submitted_at") or _utc_now()), accepted_at,
             str(values.get("note") or "")[:400], cohort_id, prospect_id))
    return {"cohort_id": cohort_id, "prospect_id": prospect_id, "outcome": outcome}


def access_result(db_path: str, cohort_id: str) -> dict:
    """The access stage only: submitted, accepted, and the preregistered verdict.

    Acceptance means LinkedIn created a channel to this person. It is not interest, not
    demand, and it is not counted anywhere downstream.
    """
    state = cohort(db_path, cohort_id)
    members = state["members"]
    n = len(members)
    submitted = [m for m in members if m["outcome"] != "not_submitted"]
    accepted = [m for m in members if m["outcome"] == "accepted"]
    pending = [m for m in members if m["outcome"] == "pending"]
    blocked = [m for m in members if m["outcome"] in ("restricted", "undeliverable")]
    k = len(accepted)
    complete = len(submitted) == n and not pending
    lo, hi = wilson(k, len(submitted)) if submitted else (0.0, 1.0)

    if not complete:
        verdict, reason = "NOT_EVALUABLE", (
            f"{len(submitted)}/{n} submitted, {len(pending)} still pending — the cohort is "
            "evaluated whole, and a partial read is how an experiment gets stopped on noise")
    elif k <= 7:
        verdict, reason = "PIVOT", f"{k}/{n} accepted, at or below the {PIVOT_RATE_CEILING:.1%} band"
    elif k < ACCEPTS_FOR_DOWNSTREAM:
        verdict, reason = "ADJUST", (
            f"{k}/{n} accepted: route viable, below the {ACCEPTS_FOR_DOWNSTREAM} accepts the "
            "downstream message test needs")
    else:
        verdict, reason = "PROCEED", f"{k}/{n} accepted, at or above {ACCEPTS_FOR_DOWNSTREAM}"

    def split(field: str) -> dict:
        out: dict[str, dict[str, int]] = {}
        for m in members:
            key = str(m[field])
            bucket = out.setdefault(key, {"in_cohort": 0, "submitted": 0, "accepted": 0})
            bucket["in_cohort"] += 1
            bucket["submitted"] += m["outcome"] != "not_submitted"
            bucket["accepted"] += m["outcome"] == "accepted"
        for bucket in out.values():
            bucket["rate"] = None if not bucket["submitted"] else bucket["accepted"] / bucket["submitted"]
        return out

    result = {
        "cohort_id": cohort_id, "cohort_size": n,
        "invitations_submitted": len(submitted), "accepted": k,
        "pending": len(pending), "blocked": len(blocked),
        "not_submitted": n - len(submitted),
        # Denominator is invitations SUBMITTED, never cohort size: an invitation that was
        # never sent is not a refusal.
        "accept_rate": None if not submitted else k / len(submitted),
        "accept_rate_ci": None if not submitted else [lo, hi],
        "complete": complete, "verdict": verdict, "reason": reason,
        "by_identity_sourcing": split("identity_sourcing"),
        "by_ownership_structure": split("ownership_structure"),
        "by_identity_confidence": split("identity_confidence"),
    }
    if verdict == "ADJUST":
        rate = k / len(submitted)
        needed_accepts = ACCEPTS_FOR_DOWNSTREAM - k
        result["expansion"] = {
            "additional_accepts_required": needed_accepts,
            "observed_accept_rate": rate,
            "additional_verified_identities_required":
                None if rate == 0 else math.ceil(needed_accepts / rate),
        }
    if verdict == "PROCEED":
        result["message_eligible_prospect_ids"] = [m["prospect_id"] for m in accepted]
    return result
