from __future__ import annotations

import json
import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

DB_LOCK = threading.RLock()
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
    conn.execute("PRAGMA foreign_keys = ON")
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


def row_to_dict(row: sqlite3.Row | None, json_fields: set[str] | None = None) -> dict[str, Any] | None:
    if row is None:
        return None
    json_fields = json_fields or set()
    out = dict(row)
    for field in json_fields:
        if field in out:
            out[field] = loads(out[field], [] if field.endswith("s") or field.endswith("json") else {})
    return out


def rows_to_dicts(rows: Iterable[sqlite3.Row], json_fields: set[str] | None = None) -> list[dict[str, Any]]:
    return [row_to_dict(row, json_fields) or {} for row in rows]


def execute(conn: sqlite3.Connection, sql: str, params: tuple[Any, ...] = ()) -> sqlite3.Cursor:
    with DB_LOCK:
        return conn.execute(sql, params)


def init_db() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    with db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE,
                username TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user',
                settings_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                expires_at TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS instructors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                slug TEXT NOT NULL UNIQUE,
                avatar_url TEXT,
                description TEXT NOT NULL DEFAULT '',
                personality TEXT NOT NULL DEFAULT '',
                voice TEXT NOT NULL DEFAULT 'browser-default',
                system_prompt TEXT NOT NULL DEFAULT '',
                created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
                is_public INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS scripts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                instructor_id INTEGER REFERENCES instructors(id) ON DELETE SET NULL,
                created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
                visibility TEXT NOT NULL DEFAULT 'public',
                tags_json TEXT NOT NULL DEFAULT '[]',
                events_json TEXT NOT NULL DEFAULT '[]',
                duration_seconds INTEGER NOT NULL DEFAULT 0,
                difficulty TEXT NOT NULL DEFAULT 'normal',
                votes INTEGER NOT NULL DEFAULT 0,
                plays INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS script_votes (
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                script_id INTEGER NOT NULL REFERENCES scripts(id) ON DELETE CASCADE,
                vote INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (user_id, script_id)
            );

            CREATE TABLE IF NOT EXISTS game_generators (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
                visibility TEXT NOT NULL DEFAULT 'public',
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
                generator_id INTEGER REFERENCES game_generators(id) ON DELETE SET NULL,
                created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
                tags_json TEXT NOT NULL DEFAULT '[]',
                events_json TEXT NOT NULL DEFAULT '[]',
                settings_json TEXT NOT NULL DEFAULT '{}',
                duration_seconds INTEGER NOT NULL DEFAULT 0,
                plays INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS dialogs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                script_id INTEGER REFERENCES scripts(id) ON DELETE CASCADE,
                instructor_id INTEGER REFERENCES instructors(id) ON DELETE SET NULL,
                created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
                title TEXT NOT NULL,
                text TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'ready',
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS media (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                media_type TEXT NOT NULL,
                url TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT 'url',
                created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
                tags_json TEXT NOT NULL DEFAULT '[]',
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS devices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                device_type TEXT NOT NULL,
                label TEXT NOT NULL,
                config_json TEXT NOT NULL DEFAULT '{}',
                status TEXT NOT NULL DEFAULT 'unknown',
                last_seen_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS device_command_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id INTEGER REFERENCES devices(id) ON DELETE SET NULL,
                user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                command_json TEXT NOT NULL,
                response_json TEXT NOT NULL DEFAULT '{}',
                status TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS challenger_rooms (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL UNIQUE,
                title TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'waiting',
                created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
                config_json TEXT NOT NULL DEFAULT '{}',
                snapshot_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                action TEXT NOT NULL,
                entity_type TEXT,
                entity_id TEXT,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_scripts_visibility ON scripts(visibility);
            CREATE INDEX IF NOT EXISTS idx_scripts_created_by ON scripts(created_by);
            CREATE INDEX IF NOT EXISTS idx_games_created_by ON games(created_by);
            CREATE INDEX IF NOT EXISTS idx_media_created_by ON media(created_by);
            CREATE INDEX IF NOT EXISTS idx_devices_user_id ON devices(user_id);
            """
        )
