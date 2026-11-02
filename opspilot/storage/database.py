from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager

from config.settings import db_path

_connections: dict[str, sqlite3.Connection] = {}

SCHEMA = """
CREATE TABLE IF NOT EXISTS incident_counter (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    value INTEGER NOT NULL
);
INSERT OR IGNORE INTO incident_counter (id, value) VALUES (1, 1000);

CREATE TABLE IF NOT EXISTS incidents (
    incident_id TEXT PRIMARY KEY,
    user_message TEXT NOT NULL,
    issue_type TEXT,
    severity TEXT,
    status TEXT NOT NULL,
    evidence_json TEXT NOT NULL DEFAULT '[]',
    investigation_json TEXT NOT NULL DEFAULT '{}',
    root_cause_json TEXT,
    confidence REAL,
    recommended_action_json TEXT,
    approval_status TEXT,
    approval_request TEXT,
    recovery_json TEXT,
    verification_json TEXT,
    final_report TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    incident_id TEXT NOT NULL,
    action TEXT NOT NULL,
    detail TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


def connect() -> sqlite3.Connection:
    path = db_path()
    key = str(path)
    connection = _connections.get(key)
    if connection is not None:
        return connection
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(key, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.executescript(SCHEMA)
    connection.commit()
    _connections[key] = connection
    return connection


@contextmanager
def transaction() -> Iterator[sqlite3.Connection]:
    connection = connect()
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise


def close_connections() -> None:
    for connection in _connections.values():
        connection.close()
    _connections.clear()
