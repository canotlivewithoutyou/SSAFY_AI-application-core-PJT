"""Small SQLite boundary used by repositories.

Keeping SQL access here makes it easy to replace the database layer later without
mixing persistence details into API routes or the planner.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


SCHEMA = """
CREATE TABLE IF NOT EXISTS visit_plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    institution_type TEXT NOT NULL CHECK (institution_type IN ('hospital', 'pharmacy')),
    institution_id TEXT,
    institution_name TEXT NOT NULL,
    institution_address TEXT NOT NULL,
    visit_date TEXT NOT NULL,
    origin_name TEXT NOT NULL,
    origin_longitude REAL NOT NULL,
    origin_latitude REAL NOT NULL,
    destination_longitude REAL NOT NULL,
    destination_latitude REAL NOT NULL,
    departure_at TEXT NOT NULL,
    expected_arrival_at TEXT NOT NULL,
    travel_duration_seconds INTEGER NOT NULL CHECK (travel_duration_seconds >= 0),
    operation_start TEXT,
    operation_end TEXT,
    selection_reason TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_visit_plans_visit_date
ON visit_plans (visit_date, departure_at);

CREATE TABLE IF NOT EXISTS execution_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    stage TEXT NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}',
    duration_ms INTEGER,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_execution_logs_session
ON execution_logs (session_id, id);
"""


@contextmanager
def connect(database_path: Path) -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(database_path, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize_database(database_path: Path) -> None:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    with connect(database_path) as connection:
        connection.execute("PRAGMA journal_mode = WAL")
        connection.executescript(SCHEMA)


def is_database_ready(database_path: Path) -> bool:
    try:
        with connect(database_path) as connection:
            connection.execute("SELECT 1").fetchone()
    except sqlite3.Error:
        return False
    return True

