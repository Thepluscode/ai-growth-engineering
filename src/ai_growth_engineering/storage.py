from __future__ import annotations

import sqlite3
from pathlib import Path


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
    kill_threshold REAL NOT NULL,
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
    notes TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS evidence (
    evidence_id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    statement TEXT NOT NULL,
    source TEXT NOT NULL,
    confidence REAL NOT NULL,
    observed INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS suppression (
    identity TEXT PRIMARY KEY,
    reason TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


def connect(db_path: str) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def init_db(db_path: str) -> None:
    with connect(db_path) as con:
        con.executescript(SCHEMA)
