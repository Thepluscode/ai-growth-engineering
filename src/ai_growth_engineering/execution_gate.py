"""Hold a preregistered experiment until another experiment's verdict is mature.

A sequencing decision ("no demand-gen test before EXP-ACQ-0006 is judged") used to live in memory
and prose. Here it is a ledger row, and every place execution would first touch the store checks it:
a canonical event, a linked send, an active campaign.

The ledger is append-only. A BLOCK names the dependency and the preregistered-gates file its verdict
is computed from; a RELEASE is appended only when that verdict is past NOT_READY on the day it is
asked for, and it records the status it saw. The frozen preregistration itself is never edited.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from .storage import connect, init_db


class GateError(ValueError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def open_blocks(con, experiment_id: str) -> list[str]:
    """Dependencies whose latest ledger row for this experiment is a BLOCK."""
    latest: dict[str, str] = {}
    for row in con.execute("SELECT depends_on, action FROM experiment_gates WHERE experiment_id = ? ORDER BY id",
                           (experiment_id,)):
        latest[row["depends_on"]] = row["action"]
    return sorted(dep for dep, action in latest.items() if action == "BLOCK")


def blocked_message(experiment_id: str, blockers: list[str]) -> str:
    return (f"{experiment_id} is PREREGISTERED_BLOCKED until the mature verdict of {', '.join(blockers)}; "
            "nothing may be generated, sent or exposed for it before `age experiment-gate release`")


def block_experiment(db_path: str, experiment_id: str, *, depends_on: str, rules_path: str, reason: str,
                     recorded_by: str = "founder") -> dict:
    from .staged_verdict import VerdictError, load_rules

    init_db(db_path)
    if not reason.strip():
        raise GateError("a block must say why it exists")
    try:
        rules = load_rules(rules_path)
    except (OSError, VerdictError) as exc:
        raise GateError(f"the dependency's preregistered gates cannot be read from {rules_path}: {exc}") from exc
    if rules.get("experiment_id") != depends_on:
        raise GateError(f"{rules_path} governs {rules.get('experiment_id')!r}, not {depends_on}")
    with connect(db_path) as con:
        if con.execute("SELECT 1 FROM experiments WHERE experiment_id = ?", (experiment_id,)).fetchone() is None:
            raise GateError(f"{experiment_id} is not preregistered")
        con.execute(
            """INSERT INTO experiment_gates(experiment_id, depends_on, action, rules_path, reason, recorded_by,
                 recorded_at) VALUES (?, ?, 'BLOCK', ?, ?, ?, ?)""",
            (experiment_id, depends_on, str(Path(rules_path)), reason.strip(), recorded_by, _now()))
    return execution_status(db_path, experiment_id)


def release_experiment(db_path: str, experiment_id: str, *, depends_on: str, as_of: str,
                       released_by: str) -> dict:
    from .staged_verdict import load_rules, verdict

    init_db(db_path)
    with connect(db_path) as con:
        if depends_on not in open_blocks(con, experiment_id):
            raise GateError(f"{experiment_id} is not blocked on {depends_on}")
        rules_path = con.execute(
            """SELECT rules_path FROM experiment_gates WHERE experiment_id = ? AND depends_on = ? AND action = 'BLOCK'
               ORDER BY id DESC LIMIT 1""", (experiment_id, depends_on)).fetchone()[0]
    result = verdict(db_path, load_rules(rules_path), as_of=as_of)
    if result["status"] == "NOT_READY":
        raise GateError(f"{depends_on} is NOT_READY on {as_of}: " + "; ".join(result.get("blockers") or [])
                        + f". {experiment_id} stays blocked.")
    with connect(db_path) as con:
        con.execute(
            """INSERT INTO experiment_gates(experiment_id, depends_on, action, rules_path, dependency_status, reason,
                 recorded_by, recorded_at) VALUES (?, ?, 'RELEASE', ?, ?, ?, ?, ?)""",
            (experiment_id, depends_on, rules_path, result["status"],
             f"{depends_on} verdict {result['status']} as of {as_of}", released_by, _now()))
    return dict(execution_status(db_path, experiment_id), dependency_status=result["status"])


def execution_status(db_path: str, experiment_id: str) -> dict:
    init_db(db_path)
    with connect(db_path) as con:
        blockers = open_blocks(con, experiment_id)
        gates = [dict(r) for r in con.execute(
            "SELECT * FROM experiment_gates WHERE experiment_id = ? ORDER BY id", (experiment_id,))]
    return {"experiment_id": experiment_id,
            "status": "PREREGISTERED_BLOCKED" if blockers else "EXECUTABLE",
            "blocked_by": blockers, "gates": gates}
