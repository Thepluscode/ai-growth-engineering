from __future__ import annotations

import csv
from dataclasses import asdict

from .models import Evidence, ExperimentDecision, ExperimentSpec
from .storage import connect


def add_evidence(db_path: str, evidence: Evidence) -> None:
    evidence.validate()
    with connect(db_path) as con:
        con.execute(
            """INSERT INTO evidence(
                 evidence_id, kind, statement, source, confidence, observed,
                 inference, observed_at, commercial_implication
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                evidence.evidence_id,
                evidence.kind.value,
                evidence.statement,
                evidence.source,
                evidence.confidence,
                int(evidence.observed),
                evidence.inference,
                evidence.observed_at,
                evidence.commercial_implication,
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
                 kill_threshold, minimum_sample, market, buyer, problem, channel,
                 control, variant, secondary_metrics, economic_metric, budget_pence,
                 start_date, end_date, learning
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                spec.experiment_id,
                spec.hypothesis,
                spec.primary_metric,
                spec.success_threshold,
                spec.kill_threshold,
                spec.minimum_sample,
                spec.market,
                spec.buyer,
                spec.problem,
                spec.channel,
                spec.control,
                spec.variant,
                "; ".join(spec.secondary_metrics),
                spec.economic_metric,
                spec.budget_pence,
                spec.start_date,
                spec.end_date,
                spec.learning,
            ),
        )
        con.executemany(
            "INSERT INTO experiment_evidence(experiment_id, evidence_id) VALUES (?, ?)",
            ((spec.experiment_id, evidence_id) for evidence_id in spec.evidence_ids),
        )


def record_experiment_result(
    db_path: str,
    experiment_id: str,
    sample_size: int,
    observed_value: float,
    learning: str = "",
) -> str:
    with connect(db_path) as con:
        row = con.execute("SELECT * FROM experiments WHERE experiment_id = ?", (experiment_id,)).fetchone()
        if row is None:
            raise ValueError("experiment not found")
        if sample_size < 0:
            raise ValueError("sample_size cannot be negative")
        if sample_size < row["minimum_sample"]:
            # A partial sample is evidence-in-progress, not a failed or invalid test.
            # EXP-ACQ-0001 explicitly forbids a final conclusion before 50 sends.
            decision = ExperimentDecision.PREREGISTERED.value
        elif observed_value >= row["success_threshold"]:
            decision = ExperimentDecision.KEEP.value
        elif observed_value < row["kill_threshold"]:
            decision = ExperimentDecision.KILL.value
        else:
            decision = ExperimentDecision.ITERATE.value
        con.execute(
            """UPDATE experiments
               SET sample_size=?, observed_value=?, decision=?, learning=?
               WHERE experiment_id=?""",
            (sample_size, observed_value, decision, learning, experiment_id),
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


def import_outreach(db_path: str, csv_path: str) -> tuple[int, int]:
    """Load a sent-outreach log into the store. Returns (imported, skipped).

    Sends get recorded in the experiment's CSV as they happen; the scoreboard reads the
    store. Without this the scoreboard reports zero outreach while ten messages are out,
    which reads as a commercial blocker that does not exist.

    Idempotent on (company, sent_at) so re-running cannot inflate the count.
    """
    imported = skipped = 0
    with open(csv_path, newline="", encoding="utf-8") as handle, connect(db_path) as con:
        for row in csv.DictReader(handle):
            company = (row.get("company") or "").strip()
            sent_at = (row.get("date_first_contact") or "").strip()
            if not company or not sent_at:
                skipped += 1
                continue
            exists = con.execute(
                "SELECT 1 FROM outreach WHERE company = ? AND sent_at = ?", (company, sent_at)
            ).fetchone()
            if exists:
                skipped += 1
                continue
            reply = (row.get("meaningful_reply") or "").strip().lower()
            con.execute(
                """INSERT INTO outreach(company, sent_at, meaningful_reply, notes)
                   VALUES (?, ?, ?, ?)""",
                (
                    company,
                    sent_at,
                    1 if reply in {"1", "true", "yes"} else 0,
                    (row.get("notes") or "").strip(),
                ),
            )
            imported += 1
    return imported, skipped


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
