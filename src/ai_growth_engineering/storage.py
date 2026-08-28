from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS prospects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company TEXT NOT NULL UNIQUE,
    website TEXT NOT NULL DEFAULT '',
    priority TEXT NOT NULL DEFAULT 'B',
    target_roles TEXT NOT NULL DEFAULT '',
    evidence TEXT NOT NULL DEFAULT '',
    source_url TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'research'
);

CREATE TABLE IF NOT EXISTS teardowns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company TEXT NOT NULL,
    observation TEXT NOT NULL,
    hypothesis TEXT NOT NULL,
    metric TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS experiments (
    experiment_id TEXT PRIMARY KEY,
    hypothesis TEXT NOT NULL,
    primary_metric TEXT NOT NULL,
    success_threshold REAL NOT NULL,
    review_threshold REAL NOT NULL,
    minimum_sample INTEGER NOT NULL,
    decision TEXT NOT NULL DEFAULT 'preregistered',
    sample_size INTEGER NOT NULL DEFAULT 0,
    observed_value REAL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS outreach (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company TEXT NOT NULL,
    sent_at TEXT,
    meaningful_reply INTEGER NOT NULL DEFAULT 0,
    discovery INTEGER NOT NULL DEFAULT 0,
    diagnostic_proposed INTEGER NOT NULL DEFAULT 0,
    proposal INTEGER NOT NULL DEFAULT 0,
    paid INTEGER NOT NULL DEFAULT 0,
    collected_revenue_pence INTEGER NOT NULL DEFAULT 0,
    notes TEXT NOT NULL DEFAULT '',
    stage TEXT NOT NULL DEFAULT 'sent_awaiting_reply',
    recipient_class TEXT NOT NULL DEFAULT 'unclassified',
    channel TEXT NOT NULL DEFAULT 'unknown'
);

CREATE TABLE IF NOT EXISTS evidence (
    evidence_id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    statement TEXT NOT NULL,
    source TEXT NOT NULL,
    confidence REAL NOT NULL,
    observed INTEGER NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS experiment_evidence (
    experiment_id TEXT NOT NULL REFERENCES experiments(experiment_id),
    evidence_id TEXT NOT NULL REFERENCES evidence(evidence_id),
    PRIMARY KEY (experiment_id, evidence_id)
);

CREATE TABLE IF NOT EXISTS experiment_trust_guardrails (
    experiment_id TEXT NOT NULL REFERENCES experiments(experiment_id),
    metric TEXT NOT NULL,
    direction TEXT NOT NULL DEFAULT 'lower_is_better',
    baseline REAL,
    max_absolute REAL,
    max_adverse_delta REAL,
    max_relative_increase REAL,
    minimum_sample INTEGER NOT NULL DEFAULT 0,
    required INTEGER NOT NULL DEFAULT 1,
    source TEXT NOT NULL DEFAULT '',
    not_applicable_reason TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (experiment_id, metric)
);

CREATE TABLE IF NOT EXISTS experiment_trust_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    experiment_id TEXT NOT NULL REFERENCES experiments(experiment_id),
    metric TEXT NOT NULL,
    numerator INTEGER NOT NULL,
    denominator INTEGER NOT NULL,
    observed_value REAL,
    observed_at TEXT NOT NULL DEFAULT '',
    evidence_id TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS suppression (
    identity TEXT PRIMARY KEY,
    reason TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


@contextmanager
def connect(db_path: str) -> Iterator[sqlite3.Connection]:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


# Columns added after the first databases existed. CREATE TABLE IF NOT EXISTS will not
# add them to a table that already exists, so they are applied explicitly.
EXPERIMENT_CONTRACT_COLUMNS = (
    ("market", "TEXT NOT NULL DEFAULT ''"),
    ("buyer", "TEXT NOT NULL DEFAULT ''"),
    ("problem", "TEXT NOT NULL DEFAULT ''"),
    ("channel", "TEXT NOT NULL DEFAULT ''"),
    ("control", "TEXT NOT NULL DEFAULT ''"),
    ("variant", "TEXT NOT NULL DEFAULT ''"),
    ("secondary_metrics", "TEXT NOT NULL DEFAULT ''"),
    ("economic_metric", "TEXT NOT NULL DEFAULT ''"),
    ("budget_pence", "INTEGER NOT NULL DEFAULT 0"),
    ("start_date", "TEXT NOT NULL DEFAULT ''"),
    ("end_date", "TEXT NOT NULL DEFAULT ''"),
    ("learning", "TEXT NOT NULL DEFAULT ''"),
)

EVIDENCE_CONTRACT_COLUMNS = (
    ("inference", "TEXT NOT NULL DEFAULT ''"),
    ("observed_at", "TEXT NOT NULL DEFAULT ''"),
    ("commercial_implication", "TEXT NOT NULL DEFAULT ''"),
    ("metadata_json", "TEXT NOT NULL DEFAULT '{}'"),
)


def _add_missing_columns(
    con: sqlite3.Connection, table: str, columns: tuple[tuple[str, str], ...]
) -> list[str]:
    existing = {row[1] for row in con.execute(f"PRAGMA table_info({table})")}
    added = []
    for name, decl in columns:
        if name not in existing:
            con.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")
            added.append(f"{table}.{name}")
    return added


def _rename_kill_to_review(con: sqlite3.Connection) -> list[str]:
    """`kill_threshold` became `review_threshold`, and the `kill` decision became `review`.

    The number is unchanged. What changed is that a result below it no longer pronounces
    on the business — it asks a person to look. Applied to existing databases so a
    preregistered experiment keeps its thresholds and its history.
    """
    columns = {row[1] for row in con.execute("PRAGMA table_info(experiments)")}
    changed: list[str] = []
    if "kill_threshold" in columns and "review_threshold" not in columns:
        con.execute("ALTER TABLE experiments RENAME COLUMN kill_threshold TO review_threshold")
        changed.append("experiments.review_threshold")
    updated = con.execute("UPDATE experiments SET decision = 'review' WHERE decision = 'kill'")
    if updated.rowcount > 0:
        changed.append(f"decision:kill->review x{updated.rowcount}")
    return changed


OUTREACH_COLUMNS = (
    ("stage", "TEXT NOT NULL DEFAULT 'sent_awaiting_reply'"),
    # Added 2026-08-27 after EXP-ACQ-0001 discovered that 48 of its 50 "qualified
    # sends" went to a shared inbox. Existing rows migrate to 'unclassified' rather
    # than to a guess: an inferred class would let the same blended rate come back
    # wearing a column name.
    ("recipient_class", "TEXT NOT NULL DEFAULT 'unclassified'"),
    # Added 2026-08-28. recipient_class answers who received it; this answers how it
    # got there. EXP-ACQ-0002's discovery closed the email route for this ICP and put
    # LinkedIn forward as the candidate replacement — two channels with different
    # delivery behaviour, and nothing in the store stopped their replies landing in one
    # rate. A rate is never computed across two channels.
    ("channel", "TEXT NOT NULL DEFAULT 'unknown'"),
)


def migrate(con: sqlite3.Connection) -> list[str]:
    """Bring an existing database up to the current schema. Returns what it added."""
    return (
        _rename_kill_to_review(con)
        + _add_missing_columns(con, "outreach", OUTREACH_COLUMNS)
        + _add_missing_columns(con, "experiments", EXPERIMENT_CONTRACT_COLUMNS)
        + _add_missing_columns(con, "evidence", EVIDENCE_CONTRACT_COLUMNS)
    )


def init_db(db_path: str) -> None:
    from .registries import migrate_columns, schema_sql

    with connect(db_path) as con:
        con.executescript(SCHEMA)
        con.executescript(schema_sql())
        migrate(con)
        migrate_columns(con)
