"""SQLite persistence, schema initialization, and database revision tracking."""
from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_DB = Path(__file__).resolve().parents[1] / "data" / "accesspath.db"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime | None = None) -> str:
    return (dt or utcnow()).isoformat(timespec="seconds")


def database_path() -> Path:
    return Path(os.environ.get("ACCESSPATH_DB", str(DEFAULT_DB))).expanduser().resolve()


@contextmanager
def connect(path: Path | str | None = None):
    target = Path(path or database_path())
    target.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(target), timeout=10, check_same_thread=False)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    db.execute("PRAGMA busy_timeout = 10000")
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


SCHEMA = """
CREATE TABLE IF NOT EXISTS nodes (
    id TEXT PRIMARY KEY,
    label TEXT NOT NULL,
    lat REAL NOT NULL,
    lon REAL NOT NULL,
    kind TEXT NOT NULL DEFAULT 'junction'
);
CREATE TABLE IF NOT EXISTS edges (
    id TEXT PRIMARY KEY,
    source TEXT NOT NULL REFERENCES nodes(id),
    target TEXT NOT NULL REFERENCES nodes(id),
    distance_m REAL NOT NULL CHECK(distance_m > 0),
    stairs INTEGER CHECK(stairs >= 0),
    slope_pct REAL CHECK(slope_pct >= 0),
    surface TEXT CHECK(surface IN ('smooth','paved','gravel','rough') OR surface IS NULL),
    curb TEXT CHECK(curb IN ('flush','ramped','high') OR curb IS NULL),
    crossing INTEGER NOT NULL DEFAULT 0,
    verification TEXT NOT NULL CHECK(verification IN ('verified','community','unverified')),
    surveyed_at TEXT,
    name TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_edges_source ON edges(source);
CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    edge_id TEXT NOT NULL REFERENCES edges(id),
    obstacle_type TEXT NOT NULL CHECK(obstacle_type IN
       ('blocked','stairs','steep_slope','broken_surface','missing_curb','temporary_obstruction')),
    severity INTEGER NOT NULL CHECK(severity BETWEEN 1 AND 3),
    description TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('pending','reviewed','verified','rejected','resolved','expired')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    expires_at TEXT,
    reviewer_note TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_reports_edge_status ON reports(edge_id, status);
CREATE TABLE IF NOT EXISTS moderation_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    report_id INTEGER NOT NULL REFERENCES reports(id),
    action TEXT NOT NULL,
    note TEXT NOT NULL,
    occurred_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS route_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    start_id TEXT NOT NULL,
    end_id TEXT NOT NULL,
    profile TEXT NOT NULL,
    algorithm TEXT NOT NULL,
    risk_aversion INTEGER NOT NULL,
    shortest_distance_m REAL,
    selected_distance_m REAL,
    selected_confidence REAL,
    computation_ms REAL NOT NULL,
    network_revision INTEGER NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS evaluation_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    network_revision INTEGER NOT NULL,
    results_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
INSERT OR IGNORE INTO settings(key, value) VALUES('network_revision', '1');
"""


def initialize(path: Path | str | None = None, seed_if_empty: bool = True) -> None:
    with connect(path) as db:
        db.executescript(SCHEMA)
        exists = db.execute("SELECT 1 FROM nodes LIMIT 1").fetchone()
        if seed_if_empty and not exists:
            from .demo_data import seed
            seed(db)


def revision(db: sqlite3.Connection) -> int:
    return int(db.execute("SELECT value FROM settings WHERE key='network_revision'").fetchone()[0])


def increment_revision(db: sqlite3.Connection) -> None:
    db.execute("UPDATE settings SET value=CAST(value AS INTEGER)+1 WHERE key='network_revision'")


def expire_reports(db: sqlite3.Connection) -> int:
    now = iso()
    cur = db.execute(
        "UPDATE reports SET status='expired', updated_at=? "
        "WHERE status IN ('pending','reviewed','verified') AND expires_at IS NOT NULL AND expires_at<=?",
        (now, now),
    )
    if cur.rowcount:
        increment_revision(db)
        db.execute(
            "INSERT INTO moderation_audit(report_id,action,note,occurred_at) "
            "SELECT id,'expire','Automatic expiration',? FROM reports "
            "WHERE status='expired' AND updated_at=?",
            (now, now),
        )
    return cur.rowcount
