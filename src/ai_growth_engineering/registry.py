from __future__ import annotations

import csv
from dataclasses import asdict

from .models import Evidence, ExperimentDecision, ExperimentSpec
from .storage import connect


def add_evidence(db_path: str, evidence: Evidence) -> None:
    evidence.validate()
    with connect(db_path) as con:
        con.execute(
            """INSERT INTO evidence(evidence_id, kind, statement, source, confidence, observed)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                evidence.evidence_id,
                evidence.kind.value,
                evidence.statement,
                evidence.source,
                evidence.confidence,
                int(evidence.observed),
            ),
        )


def add_experiment(db_path: str, spec: ExperimentSpec) -> None:
    spec.validate()
    with connect(db_path) as con:
        if spec.evidence_ids:
            placeholders = ",".join("?" for _ in spec.evidence_ids)
            count = con.execute(
                f"SELECT COUNT(*) FROM evidence WHERE evidence_id IN ({placeholders})",
                spec.evidence_ids,
            ).fetchone()[0]
            if count != len(set(spec.evidence_ids)):
                raise ValueError("all referenced evidence_ids must exist")
        con.execute(
            """INSERT INTO experiments(
                 experiment_id, hypothesis, primary_metric, success_threshold,
                 kill_threshold, minimum_sample
               ) VALUES (?, ?, ?, ?, ?, ?)""",
            (
                spec.experiment_id,
                spec.hypothesis,
                spec.primary_metric,
                spec.success_threshold,
                spec.kill_threshold,
                spec.minimum_sample,
            ),
        )


def record_experiment_result(db_path: str, experiment_id: str, sample_size: int, observed_value: float) -> str:
    with connect(db_path) as con:
        row = con.execute("SELECT * FROM experiments WHERE experiment_id = ?", (experiment_id,)).fetchone()
        if row is None:
            raise ValueError("experiment not found")
        if sample_size < row["minimum_sample"]:
            decision = ExperimentDecision.INVALID.value
        elif observed_value >= row["success_threshold"]:
            decision = ExperimentDecision.KEEP.value
        elif observed_value < row["kill_threshold"]:
            decision = ExperimentDecision.KILL.value
        else:
            decision = ExperimentDecision.ITERATE.value
        con.execute(
            "UPDATE experiments SET sample_size=?, observed_value=?, decision=? WHERE experiment_id=?",
            (sample_size, observed_value, decision, experiment_id),
        )
        return decision


def seed_prospects(db_path: str, csv_path: str) -> int:
    count = 0
    with open(csv_path, newline="", encoding="utf-8") as handle, connect(db_path) as con:
        reader = csv.DictReader(handle)
        for row in reader:
            con.execute(
                """INSERT OR IGNORE INTO prospects(
                     company, website, priority, target_roles, evidence, source_url, status
                   ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    row["company"], row.get("website", ""), row.get("priority", "B"),
                    row.get("target_roles", ""), row.get("evidence", ""),
                    row.get("source_url", ""), row.get("status", "research"),
                ),
            )
            count += 1
    return count


def scoreboard(db_path: str) -> dict[str, int]:
    with connect(db_path) as con:
        return {
            "qualified_prospects": con.execute(
                "SELECT COUNT(*) FROM prospects WHERE status NOT LIKE 'disqualified%'"
            ).fetchone()[0],
            "outreach_sent": con.execute("SELECT COUNT(*) FROM outreach WHERE sent_at IS NOT NULL").fetchone()[0],
            "meaningful_responses": con.execute("SELECT COALESCE(SUM(meaningful_reply),0) FROM outreach").fetchone()[0],
            "discovery_calls": con.execute("SELECT COALESCE(SUM(discovery),0) FROM outreach").fetchone()[0],
            "diagnostics_proposed": con.execute("SELECT COALESCE(SUM(diagnostic_proposed),0) FROM outreach").fetchone()[0],
            "commercial_proposals": con.execute("SELECT COALESCE(SUM(proposal),0) FROM outreach").fetchone()[0],
            "paying_customers": con.execute("SELECT COALESCE(SUM(paid),0) FROM outreach").fetchone()[0],
            "collected_revenue_pence": con.execute("SELECT COALESCE(SUM(collected_revenue_pence),0) FROM outreach").fetchone()[0],
        }
