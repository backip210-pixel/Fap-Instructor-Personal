from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

DATA_DIR = Path(os.getenv("DATA_DIR", "/data"))
DB_PATH = DATA_DIR / "app.db"
UPLOAD_DIR = DATA_DIR / "uploads"


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def loads(value: str | bytes | None, fallback: Any = None) -> Any:
    if value in (None, ""):
        return fallback
    try:
        return json.loads(value)  # type: ignore[arg-type]
    except Exception:
        return fallback


def connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


@contextmanager
def db() -> Iterable[sqlite3.Connection]:
    conn = connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    cols = {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def init_db() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    with db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS scripts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                tags_json TEXT NOT NULL DEFAULT '[]',
                events_json TEXT NOT NULL DEFAULT '[]',
                duration_seconds INTEGER NOT NULL DEFAULT 0,
                difficulty TEXT NOT NULL DEFAULT 'normal',
                votes INTEGER NOT NULL DEFAULT 0,
                plays INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS game_generators (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                tags_json TEXT NOT NULL DEFAULT '[]',
                config_json TEXT NOT NULL DEFAULT '{}',
                runs INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS games (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                generator_id INTEGER,
                tags_json TEXT NOT NULL DEFAULT '[]',
                events_json TEXT NOT NULL DEFAULT '[]',
                settings_json TEXT NOT NULL DEFAULT '{}',
                duration_seconds INTEGER NOT NULL DEFAULT 0,
                plays INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS media (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                media_type TEXT NOT NULL,
                url TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT 'url',
                tags_json TEXT NOT NULL DEFAULT '[]',
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_scripts_updated ON scripts(updated_at);
            CREATE INDEX IF NOT EXISTS idx_games_updated ON games(updated_at);
            CREATE INDEX IF NOT EXISTS idx_media_updated ON media(updated_at);
            """
        )

        # Compatibility with older local volumes from previous builds.
        for column, definition in {
            "tags_json": "TEXT NOT NULL DEFAULT '[]'",
            "events_json": "TEXT NOT NULL DEFAULT '[]'",
            "duration_seconds": "INTEGER NOT NULL DEFAULT 0",
            "difficulty": "TEXT NOT NULL DEFAULT 'normal'",
            "votes": "INTEGER NOT NULL DEFAULT 0",
            "plays": "INTEGER NOT NULL DEFAULT 0",
            "created_at": "TEXT NOT NULL DEFAULT ''",
            "updated_at": "TEXT NOT NULL DEFAULT ''",
        }.items():
            _ensure_column(conn, "scripts", column, definition)

        for column, definition in {
            "tags_json": "TEXT NOT NULL DEFAULT '[]'",
            "config_json": "TEXT NOT NULL DEFAULT '{}'",
            "runs": "INTEGER NOT NULL DEFAULT 0",
            "created_at": "TEXT NOT NULL DEFAULT ''",
            "updated_at": "TEXT NOT NULL DEFAULT ''",
        }.items():
            _ensure_column(conn, "game_generators", column, definition)
