"""A PII-free, deterministic summary of repository and store state, for documentation to cite.

Documentation retypes numbers and the numbers drift. Instead, `age snapshot --write docs/STATE.json`
generates them: capability inventory from `capability_map.json`, and from the private store only
counts, statuses, bases and a hash of the event ids. No company, person, address or free text leaves
the store through this file. There is no timestamp in it, so regenerating an unchanged store
produces an identical file and `scripts/docs_check.py` can compare the two.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from . import capabilities
from .storage import connect

SCHEMA = "age-state.v1"


def capability_state() -> dict:
    data = capabilities.load()
    capabilities.validate(data)
    totals = capabilities.counts(data)
    return {"total": sum(totals.values()), "domains": len(data["domains"]),
            **{status: totals.get(status, 0) for status in capabilities.STATUSES}}


def store_state(db_path: str) -> dict:
    from .execution_gate import execution_status
    from .funnel_events import effective_events, synthetic_count
    from .registry import canonical_sample, reconcile_experiments, scoreboard_basis, trust_policy
    from .reply_capture import pending_count

    events = effective_events(db_path)
    by_experiment: dict[str, Counter] = {}
    for event in events:
        by_experiment.setdefault(event["experiment_id"] or "(unassigned)", Counter())[event["event_type"]] += 1
    with connect(db_path) as con:
        ids = [r[0] for r in con.execute("SELECT event_id FROM funnel_events ORDER BY event_id")]
        corrections = con.execute("SELECT COUNT(*) FROM funnel_events WHERE event_type = 'correction'").fetchone()[0]
        conflicts = con.execute("SELECT COUNT(*) FROM idempotency_conflicts").fetchone()[0]
        experiment_rows = [dict(r) for r in con.execute(
            "SELECT experiment_id, decision, sample_size FROM experiments ORDER BY experiment_id")]
    reconciliation = {(r["experiment_id"], r["metric"]): r["status"] for r in reconcile_experiments(db_path)}
    experiments = {}
    for row in experiment_rows:
        exp = row["experiment_id"]
        experiments[exp] = {
            "decision": row["decision"], "stored_sample": row["sample_size"],
            "computed_sample": canonical_sample(db_path, exp),
            "sample_reconciliation": reconciliation[(exp, "sample_size")],
            "trust_policy": trust_policy(db_path, exp)["state"],
            "execution": execution_status(db_path, exp)["status"],
        }
    return {
        "events": {
            "rows": len(ids), "effective": len(events), "corrections": corrections,
            "synthetic_excluded": synthetic_count(db_path),
            "log_sha256": hashlib.sha256("\n".join(ids).encode()).hexdigest(),
            "by_type": dict(sorted(Counter(e["event_type"] for e in events).items())),
            "by_experiment": {k: dict(sorted(v.items())) for k, v in sorted(by_experiment.items())},
        },
        "experiments": experiments,
        "scoreboard": {r["metric"]: {"value": r["value"], "basis": r["basis"], "diverges": r["diverges"]}
                       for r in scoreboard_basis(db_path)},
        "idempotency_conflicts": conflicts,
        "pending_reply_reviews": pending_count(db_path),
    }


def snapshot(db_path: str) -> dict:
    return {"schema": SCHEMA, "capabilities": capability_state(), "store": store_state(db_path)}


def write(db_path: str, path: str | Path) -> dict:
    state = snapshot(db_path)
    Path(path).write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return state


def flatten(data: Any, prefix: str = "") -> dict[str, Any]:
    if not isinstance(data, dict):
        return {prefix: data}
    out: dict[str, Any] = {}
    for key, value in data.items():
        out.update(flatten(value, f"{prefix}.{key}" if prefix else str(key)))
    return out
