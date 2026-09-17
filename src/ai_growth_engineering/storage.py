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

CREATE TABLE IF NOT EXISTS outbound_drafts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    prospect_id INTEGER NOT NULL REFERENCES prospects(id),
    company TEXT NOT NULL,
    recipient_identity TEXT NOT NULL,
    recipient_class TEXT NOT NULL,
    channel TEXT NOT NULL,
    observation TEXT NOT NULL,
    economic_hypothesis TEXT NOT NULL,
    cta TEXT NOT NULL,
    metric TEXT NOT NULL,
    source_url TEXT NOT NULL,
    message TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending_approval',
    outreach_id INTEGER REFERENCES outreach(id),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    approved_at TEXT,
    sent_at TEXT,
    replied_at TEXT,
    rejected_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_outbound_drafts_status
ON outbound_drafts(status, created_at);

CREATE TABLE IF NOT EXISTS execution_cohort (
    cohort_id TEXT NOT NULL,
    prospect_id INTEGER NOT NULL REFERENCES prospects(id),
    identity_id INTEGER NOT NULL REFERENCES prospect_identities(id),
    identity_value TEXT NOT NULL,
    frozen_at TEXT NOT NULL,
    identity_confidence REAL NOT NULL,
    identity_sourcing TEXT NOT NULL,
    ownership_structure TEXT NOT NULL DEFAULT 'UNKNOWN',
    PRIMARY KEY (cohort_id, prospect_id)
);

CREATE TABLE IF NOT EXISTS invitations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cohort_id TEXT NOT NULL,
    prospect_id INTEGER NOT NULL REFERENCES prospects(id),
    treatment TEXT NOT NULL,
    submitted_at TEXT NOT NULL DEFAULT '',
    outcome TEXT NOT NULL DEFAULT 'not_submitted',
    accepted_at TEXT NOT NULL DEFAULT '',
    note TEXT NOT NULL DEFAULT '',
    UNIQUE(cohort_id, prospect_id)
);

CREATE TABLE IF NOT EXISTS sourcing_runs (
    run_id TEXT PRIMARY KEY,
    ran_at TEXT NOT NULL,
    source TEXT NOT NULL,
    raw_candidates INTEGER NOT NULL CHECK(raw_candidates >= 0),
    website_evidenced INTEGER NOT NULL CHECK(website_evidenced >= 0),
    qualified INTEGER NOT NULL CHECK(qualified >= 0),
    borderline INTEGER NOT NULL DEFAULT 0,
    rejected INTEGER NOT NULL DEFAULT 0,
    identity_resolved INTEGER NOT NULL DEFAULT 0,
    notes TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS intent_signals (
    signal_id TEXT PRIMARY KEY,
    prospect_id INTEGER NOT NULL REFERENCES prospects(id),
    person_name TEXT NOT NULL DEFAULT '',
    person_role TEXT NOT NULL DEFAULT '',
    signal_type TEXT NOT NULL,
    source_url TEXT NOT NULL,
    observed_fact TEXT NOT NULL,
    commercial_interpretation TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    confidence REAL NOT NULL CHECK(confidence >= 0 AND confidence <= 1),
    strength INTEGER NOT NULL CHECK(strength BETWEEN 1 AND 5),
    freshness_half_life_days INTEGER NOT NULL CHECK(freshness_half_life_days > 0),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_intent_signals_prospect_observed
ON intent_signals(prospect_id, observed_at DESC);

CREATE TABLE IF NOT EXISTS prospect_identities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    prospect_id INTEGER NOT NULL REFERENCES prospects(id),
    identity_type TEXT NOT NULL,
    value TEXT NOT NULL,
    provider TEXT NOT NULL,
    verification_status TEXT NOT NULL,
    source_url TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    confidence REAL NOT NULL CHECK(confidence >= 0 AND confidence <= 1),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(prospect_id, identity_type, value)
);

CREATE INDEX IF NOT EXISTS idx_prospect_identities_prospect
ON prospect_identities(prospect_id, verification_status);

CREATE TABLE IF NOT EXISTS draft_signal_lineage (
    draft_id INTEGER NOT NULL REFERENCES outbound_drafts(id),
    signal_id TEXT NOT NULL REFERENCES intent_signals(signal_id),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(draft_id, signal_id)
);

-- Canonical funnel events. Append-only: a wrong event is voided by a correction row, never
-- rewritten, so every past report can be rebuilt from the log as it stood.
CREATE TABLE IF NOT EXISTS funnel_events (
    event_id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    stage TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    person_id TEXT NOT NULL DEFAULT '',
    company_id INTEGER,
    company TEXT NOT NULL DEFAULT '',
    campaign_id TEXT NOT NULL DEFAULT '',
    creative_id TEXT NOT NULL DEFAULT '',
    audience_id TEXT NOT NULL DEFAULT '',
    channel TEXT NOT NULL DEFAULT '',
    experiment_id TEXT NOT NULL DEFAULT '',
    arm TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL,
    source_record_id TEXT NOT NULL,
    quantity INTEGER NOT NULL DEFAULT 1 CHECK(quantity >= 1),
    value_pence INTEGER NOT NULL DEFAULT 0 CHECK(value_pence >= 0),
    currency TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    provenance TEXT NOT NULL,
    corrects_event_id TEXT REFERENCES funnel_events(event_id),
    recorded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(source, source_record_id, event_type)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_funnel_events_one_correction
ON funnel_events(corrects_event_id) WHERE corrects_event_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_funnel_events_experiment
ON funnel_events(experiment_id, event_type, occurred_at);

CREATE TRIGGER IF NOT EXISTS funnel_events_no_update BEFORE UPDATE ON funnel_events
BEGIN SELECT RAISE(ABORT, 'funnel_events is append-only: append a correction instead'); END;

CREATE TRIGGER IF NOT EXISTS funnel_events_no_delete BEFORE DELETE ON funnel_events
BEGIN SELECT RAISE(ABORT, 'funnel_events is append-only: append a correction instead'); END;

-- A source identity that arrived again saying something different. The stored event is kept;
-- the disagreement is recorded here instead of vanishing. Append-only.
CREATE TABLE IF NOT EXISTS idempotency_conflicts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL REFERENCES funnel_events(event_id),
    source TEXT NOT NULL,
    source_record_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    differing_fields TEXT NOT NULL,
    stored_json TEXT NOT NULL,
    attempted_json TEXT NOT NULL,
    detected_at TEXT NOT NULL
);

CREATE TRIGGER IF NOT EXISTS idempotency_conflicts_no_update BEFORE UPDATE ON idempotency_conflicts
BEGIN SELECT RAISE(ABORT, 'idempotency_conflicts is append-only'); END;

CREATE TRIGGER IF NOT EXISTS idempotency_conflicts_no_delete BEFORE DELETE ON idempotency_conflicts
BEGIN SELECT RAISE(ABORT, 'idempotency_conflicts is append-only'); END;

-- A person's reading of who an event reached. The event itself is never edited. Append-only.
CREATE TABLE IF NOT EXISTS recipient_class_reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL REFERENCES funnel_events(event_id),
    recipient_class TEXT NOT NULL CHECK(recipient_class IN ('named_buyer', 'role_inbox', 'other')),
    reason TEXT NOT NULL,
    reviewed_by TEXT NOT NULL,
    reviewed_at TEXT NOT NULL
);

CREATE TRIGGER IF NOT EXISTS recipient_class_reviews_no_update BEFORE UPDATE ON recipient_class_reviews
BEGIN SELECT RAISE(ABORT, 'recipient_class_reviews is append-only'); END;

CREATE TRIGGER IF NOT EXISTS recipient_class_reviews_no_delete BEFORE DELETE ON recipient_class_reviews
BEGIN SELECT RAISE(ABORT, 'recipient_class_reviews is append-only'); END;

-- What a buyer said, related to who said it and the commercial event it arrived through. The
-- observation itself is an ordinary `evidence` row; this table only links it. Append-only.
CREATE TABLE IF NOT EXISTS commercial_evidence (
    link_id TEXT PRIMARY KEY,
    evidence_id TEXT NOT NULL REFERENCES evidence(evidence_id),
    category TEXT NOT NULL,
    person_id TEXT NOT NULL DEFAULT '',
    company TEXT NOT NULL DEFAULT '',
    occurred_at TEXT NOT NULL,
    source TEXT NOT NULL,
    source_record_id TEXT NOT NULL,
    source_event_id TEXT REFERENCES funnel_events(event_id),
    experiment_id TEXT NOT NULL DEFAULT '',
    campaign_id TEXT NOT NULL DEFAULT '',
    offer_id TEXT NOT NULL DEFAULT '',
    provenance TEXT NOT NULL,
    recorded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(evidence_id, category)
);

-- A reading of one linked observation. A new reading is appended; the latest one is current.
CREATE TABLE IF NOT EXISTS evidence_interpretations (
    interpretation_id TEXT PRIMARY KEY,
    link_id TEXT NOT NULL REFERENCES commercial_evidence(link_id),
    theme TEXT NOT NULL,
    interpretation TEXT NOT NULL,
    confidence REAL NOT NULL CHECK(confidence >= 0 AND confidence <= 1),
    interpreted_by TEXT NOT NULL,
    recorded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TRIGGER IF NOT EXISTS commercial_evidence_no_update BEFORE UPDATE ON commercial_evidence
BEGIN SELECT RAISE(ABORT, 'commercial_evidence is append-only'); END;

CREATE TRIGGER IF NOT EXISTS commercial_evidence_no_delete BEFORE DELETE ON commercial_evidence
BEGIN SELECT RAISE(ABORT, 'commercial_evidence is append-only'); END;

CREATE TRIGGER IF NOT EXISTS evidence_interpretations_no_update BEFORE UPDATE ON evidence_interpretations
BEGIN SELECT RAISE(ABORT, 'interpretations are append-only: append a new reading'); END;

CREATE TRIGGER IF NOT EXISTS evidence_interpretations_no_delete BEFORE DELETE ON evidence_interpretations
BEGIN SELECT RAISE(ABORT, 'interpretations are append-only: append a new reading'); END;

-- Governed outbound messages: which buyer and experiment a sent message belongs to. Lineage for
-- matching replies only; sends are counted by funnel events, never here.
CREATE TABLE IF NOT EXISTS outbound_messages (
    message_id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    thread_id TEXT NOT NULL,
    recipient TEXT NOT NULL,
    company TEXT NOT NULL,
    person_id TEXT NOT NULL DEFAULT '',
    experiment_id TEXT NOT NULL,
    campaign_id TEXT NOT NULL DEFAULT '',
    sent_at TEXT NOT NULL,
    recorded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_outbound_messages_thread ON outbound_messages(source, thread_id);
CREATE INDEX IF NOT EXISTS idx_outbound_messages_recipient ON outbound_messages(recipient);

-- An inbound message and what it might establish. A proposal, never a fact: nothing reaches
-- funnel_events or buyer evidence except through an approved decision.
CREATE TABLE IF NOT EXISTS reply_candidates (
    candidate_id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    source_record_id TEXT NOT NULL,
    source_thread_id TEXT NOT NULL DEFAULT '',
    sender TEXT NOT NULL,
    subject TEXT NOT NULL DEFAULT '',
    occurred_at TEXT NOT NULL,
    body TEXT NOT NULL,
    kind TEXT NOT NULL,
    match_state TEXT NOT NULL,
    match_method TEXT NOT NULL DEFAULT '',
    match_confidence TEXT NOT NULL DEFAULT '',
    company TEXT NOT NULL DEFAULT '',
    person_id TEXT NOT NULL DEFAULT '',
    experiment_id TEXT NOT NULL DEFAULT '',
    campaign_id TEXT NOT NULL DEFAULT '',
    proposals_json TEXT NOT NULL,
    captured_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(source, source_record_id)
);

-- One human decision per proposed item. Append-only; a rejection is kept so the message is never
-- proposed again, and it is never buyer evidence.
CREATE TABLE IF NOT EXISTS reply_decisions (
    candidate_id TEXT NOT NULL REFERENCES reply_candidates(candidate_id),
    item TEXT NOT NULL,
    decision TEXT NOT NULL CHECK(decision IN ('APPROVED', 'REJECTED')),
    detail_json TEXT NOT NULL DEFAULT '{}',
    result_ref TEXT NOT NULL DEFAULT '',
    decided_by TEXT NOT NULL,
    decided_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (candidate_id, item)
);

-- When a governed reply check ran. A no-response verdict needs a check made after its window.
CREATE TABLE IF NOT EXISTS reply_checks (
    check_id INTEGER PRIMARY KEY AUTOINCREMENT,
    experiment_id TEXT NOT NULL,
    checked_at TEXT NOT NULL,
    messages_in_payload INTEGER NOT NULL,
    summary_json TEXT NOT NULL
);

CREATE TRIGGER IF NOT EXISTS reply_checks_no_update BEFORE UPDATE ON reply_checks
BEGIN SELECT RAISE(ABORT, 'reply checks are append-only'); END;

CREATE TRIGGER IF NOT EXISTS reply_candidates_no_update BEFORE UPDATE ON reply_candidates
BEGIN SELECT RAISE(ABORT, 'reply candidates are captured once and never rewritten'); END;

CREATE TRIGGER IF NOT EXISTS reply_decisions_no_update BEFORE UPDATE ON reply_decisions
BEGIN SELECT RAISE(ABORT, 'reply decisions are append-only'); END;

CREATE TRIGGER IF NOT EXISTS reply_decisions_no_delete BEFORE DELETE ON reply_decisions
BEGIN SELECT RAISE(ABORT, 'reply decisions are append-only'); END;

-- A pending review is resolved by a decision, never by removing the candidate; a reply check that
-- ran is a fact a verdict depends on. Neither may be deleted.
CREATE TRIGGER IF NOT EXISTS reply_candidates_no_delete BEFORE DELETE ON reply_candidates
BEGIN SELECT RAISE(ABORT, 'reply_candidates is append-only: record a decision instead'); END;

CREATE TRIGGER IF NOT EXISTS reply_checks_no_delete BEFORE DELETE ON reply_checks
BEGIN SELECT RAISE(ABORT, 'reply_checks is append-only'); END;

-- Which exact procedure version an experiment declared, before its first exposure: the variable of
-- one arm, or an input held constant across every arm (arm ''). Frozen once written.
CREATE TABLE IF NOT EXISTS experiment_procedures (
    experiment_id TEXT NOT NULL REFERENCES experiments(experiment_id),
    arm TEXT NOT NULL DEFAULT '',
    procedure_id TEXT NOT NULL,
    procedure_ref TEXT NOT NULL,
    procedure_version TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('VARIABLE', 'COMMON_INPUT')),
    frozen_by TEXT NOT NULL,
    frozen_at TEXT NOT NULL,
    PRIMARY KEY (experiment_id, arm, procedure_id)
);

CREATE TRIGGER IF NOT EXISTS experiment_procedures_no_update BEFORE UPDATE ON experiment_procedures
BEGIN SELECT RAISE(ABORT, 'a declared procedure is frozen: a new version is a new experimental condition'); END;

CREATE TRIGGER IF NOT EXISTS experiment_procedures_no_delete BEFORE DELETE ON experiment_procedures
BEGIN SELECT RAISE(ABORT, 'a declared procedure is frozen: a new version is a new experimental condition'); END;

CREATE TRIGGER IF NOT EXISTS linked_observation_frozen
BEFORE UPDATE OF statement, source, observed_at, kind ON evidence
WHEN EXISTS (SELECT 1 FROM commercial_evidence WHERE evidence_id = OLD.evidence_id)
BEGIN SELECT RAISE(ABORT, 'a linked buyer observation is never rewritten: record a new evidence row'); END;
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
    ("variable", "TEXT NOT NULL DEFAULT ''"),
    # How the frozen contract is being executed. Annotates the contract; never rewrites it.
    ("execution_mode", "TEXT NOT NULL DEFAULT ''"),
    ("execution_mode_reason", "TEXT NOT NULL DEFAULT ''"),
    # Where `variable` came from. A retrospective value makes an already-declared design explicit.
    ("variable_metadata_source", "TEXT NOT NULL DEFAULT ''"),
    ("variable_metadata_note", "TEXT NOT NULL DEFAULT ''"),
    # The trust policy. UNDECLARED can never contribute to KEEP; DECLARED means guardrails
    # exist; NOT_APPLICABLE needs a reason. Existing experiments migrate to UNDECLARED
    # rather than to a guess — a policy nobody wrote down is not a policy.
    ("trust_policy_state", "TEXT NOT NULL DEFAULT 'UNDECLARED'"),
    ("trust_policy_reason", "TEXT NOT NULL DEFAULT ''"),
    ("trust_policy_declared_at", "TEXT NOT NULL DEFAULT ''"),
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


def _separate_legacy_revenue_signal_table(con: sqlite3.Connection) -> None:
    """Move the brief evidence-led signal schema away from the operational table name."""
    columns = {row[1] for row in con.execute("PRAGMA table_info(intent_signals)")}
    if not columns or "source_url" in columns or "evidence_id" not in columns:
        return
    revenue_table = con.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'revenue_intent_signals'"
    ).fetchone()
    if revenue_table:
        raise RuntimeError("Both legacy and current revenue signal tables exist; manual review required")
    con.execute("ALTER TABLE intent_signals RENAME TO revenue_intent_signals")


def init_db(db_path: str) -> None:
    from .registries import migrate_columns, schema_sql

    with connect(db_path) as con:
        _separate_legacy_revenue_signal_table(con)
        con.executescript(SCHEMA)
        con.executescript(schema_sql())
        migrate(con)
        migrate_columns(con)
