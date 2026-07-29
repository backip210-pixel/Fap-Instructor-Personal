from __future__ import annotations

import os
import secrets
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from fastapi import Body, Depends, FastAPI, File, Form, HTTPException, Query, Response, UploadFile, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from .database import UPLOAD_DIR, db, dumps, loads, row_to_dict, rows_to_dicts, utcnow
from .game import EVENT_CATALOG, compute_duration, events_to_funscript, generate_game_from_config, normalize_events, slugify
from .integrations import send_device_command, test_device, upload_handy_script
from .security import clear_session, create_session, hash_password, require_admin, require_user, verify_password, websocket_user

APP_NAME = os.getenv("APP_NAME", "Fap Instructor Personal")
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "http://localhost:8080")
ALLOW_REGISTRATION = os.getenv("ALLOW_REGISTRATION", "true").lower() == "true"
SEED_DEMO_DATA = os.getenv("SEED_DEMO_DATA", "true").lower() == "true"
LANGUAGETOOL_API = os.getenv("LANGUAGETOOL_API", "").rstrip("/")

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(title=APP_NAME, version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[PUBLIC_BASE_URL, "http://localhost:8080", "http://127.0.0.1:8080"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def public_user(user: dict[str, Any] | None) -> dict[str, Any] | None:
    if not user:
        return None
    settings = user.get("settings") if "settings" in user else user.get("settings_json", {})
    if isinstance(settings, str):
        settings = loads(settings, {})
    return {
        "id": user["id"],
        "email": user["email"],
        "username": user["username"],
        "role": user["role"],
        "settings": settings or {},
        "createdAt": user["created_at"],
    }


def audit(user_id: int | None, action: str, entity_type: str | None = None, entity_id: str | int | None = None, metadata: dict[str, Any] | None = None) -> None:
    with db() as conn:
        conn.execute(
            "INSERT INTO audit_log(user_id, action, entity_type, entity_id, metadata_json, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, action, entity_type, str(entity_id) if entity_id is not None else None, dumps(metadata or {}), utcnow()),
        )


def script_dict(row: Any) -> dict[str, Any]:
    d = dict(row)
    d["tags"] = loads(d.pop("tags_json", "[]"), [])
    d["events"] = loads(d.pop("events_json", "[]"), [])
    d["durationSeconds"] = d.pop("duration_seconds", 0)
    d.pop("required_subscription", None)  # legacy column from older personal builds
    d["createdBy"] = {"id": d.pop("created_by", None), "username": d.pop("created_by_username", None)}
    d["instructor"] = {"id": d.get("instructor_id"), "name": d.pop("instructor_name", None)} if d.get("instructor_id") else None
    d["createdAt"] = d.pop("created_at", None)
    d["updatedAt"] = d.pop("updated_at", None)
    return d


def generator_dict(row: Any) -> dict[str, Any]:
    d = dict(row)
    d["tags"] = loads(d.pop("tags_json", "[]"), [])
    d["config"] = loads(d.pop("config_json", "{}"), {})
    d["createdBy"] = {"id": d.pop("created_by", None), "username": d.pop("created_by_username", None)}
    d["createdAt"] = d.pop("created_at", None)
    d["updatedAt"] = d.pop("updated_at", None)
    return d


def game_dict(row: Any) -> dict[str, Any]:
    d = dict(row)
    d["tags"] = loads(d.pop("tags_json", "[]"), [])
    d["events"] = loads(d.pop("events_json", "[]"), [])
    d["settings"] = loads(d.pop("settings_json", "{}"), {})
    d["durationSeconds"] = d.pop("duration_seconds", 0)
    d.pop("required_subscription", None)  # legacy column from older personal builds
    d["createdBy"] = {"id": d.pop("created_by", None), "username": d.pop("created_by_username", None)}
    d["createdAt"] = d.pop("created_at", None)
    d["updatedAt"] = d.pop("updated_at", None)
    return d


def media_dict(row: Any) -> dict[str, Any]:
    d = dict(row)
    d["tags"] = loads(d.pop("tags_json", "[]"), [])
    d["metadata"] = loads(d.pop("metadata_json", "{}"), {})
    d["mediaType"] = d.pop("media_type", "")
    d["createdBy"] = {"id": d.pop("created_by", None), "username": d.pop("created_by_username", None)}
    d["createdAt"] = d.pop("created_at", None)
    d["updatedAt"] = d.pop("updated_at", None)
    return d


def device_dict(row: Any, include_config: bool = True) -> dict[str, Any]:
    d = dict(row)
    d["deviceType"] = d.pop("device_type", "")
    d["config"] = loads(d.pop("config_json", "{}"), {}) if include_config else {}
    d["lastSeenAt"] = d.pop("last_seen_at", None)
    d["createdAt"] = d.pop("created_at", None)
    d["updatedAt"] = d.pop("updated_at", None)
    return d


def require_script_access(script_id: int, user: dict[str, Any]) -> Any:
    with db() as conn:
        row = conn.execute(
            """
            SELECT s.*, u.username AS created_by_username, i.name AS instructor_name
            FROM scripts s
            LEFT JOIN users u ON u.id = s.created_by
            LEFT JOIN instructors i ON i.id = s.instructor_id
            WHERE s.id = ?
            """,
            (script_id,),
        ).fetchone()
        if not row:
            raise HTTPException(404, "Script not found")
        if row["visibility"] != "public" and row["created_by"] != user["id"] and user.get("role") != "admin":
            raise HTTPException(403, "Not allowed")
        return row


def seed_data() -> None:
    from .database import init_db

    init_db()
    now = utcnow()
    admin_email = os.getenv("SEED_ADMIN_EMAIL", "admin@example.com").lower().strip()
    admin_password = os.getenv("SEED_ADMIN_PASSWORD", "admin123!")
    with db() as conn:
        user_count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        if user_count == 0:
            conn.execute(
                "INSERT INTO users(email, username, password_hash, role, settings_json, created_at, updated_at) VALUES (?, ?, ?, 'admin', ?, ?, ?)",
                (admin_email, "Admin", hash_password(admin_password), dumps({"theme": "dark", "tts": True, "metronomeAudio": True}), now, now),
            )
        admin_id = conn.execute("SELECT id FROM users WHERE role='admin' ORDER BY id LIMIT 1").fetchone()[0]
        if conn.execute("SELECT COUNT(*) FROM instructors").fetchone()[0] == 0:
            instructors = [
                ("Coach Nova", "coach-nova", "Focused pacing and safety checks.", "firm, concise, consent-aware", "browser-default"),
                ("Muse Velvet", "muse-velvet", "Playful timing, encouragement, and soft resets.", "warm, teasing, supportive", "browser-default"),
                ("Ritual Guide", "ritual-guide", "Structured sessions with countdowns and interactive choices.", "calm, ceremonial, precise", "browser-default"),
            ]
            for name, slug, desc, personality, voice in instructors:
                conn.execute(
                    "INSERT INTO instructors(name, slug, description, personality, voice, system_prompt, created_by, is_public, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?)",
                    (name, slug, desc, personality, f"{voice}:{slug}", "Generate short, consensual, adult-only instruction lines. Avoid unsafe coercion.", admin_id, now, now),
                )
        if SEED_DEMO_DATA and conn.execute("SELECT COUNT(*) FROM scripts").fetchone()[0] == 0:
            instructor_id = conn.execute("SELECT id FROM instructors ORDER BY id LIMIT 1").fetchone()[0]
            events = normalize_events([
                {"type": "chat-message", "text": "Welcome. Confirm you are 18+ and stop if anything feels unsafe.", "speech": "Welcome. Confirm you are 18 plus and stop if anything feels unsafe.", "duration": 5},
                {"type": "metronome", "tempo": 60, "measure": "4/4"},
                {"type": "stroke", "tempo": 60, "duration": 18, "grip": "light", "style": "full", "hand": "dominant"},
                {"type": "wait", "duration": 8},
                {"type": "stroke", "tempo": 88, "duration": 22, "grip": "normal", "style": "short", "hand": "dominant"},
                {"type": "instruction", "title": "Check in", "description": "Hydrate, slow down, or continue. Your limits win.", "duration": 8, "options": [{"title": "Continue", "events": []}, {"title": "Slow down", "events": [{"type": "stroke-tempo", "tempo": 50}]}]},
                {"type": "stroke", "tempo": 110, "duration": 18, "grip": "normal", "style": "full"},
                {"type": "orgasm", "orgasm": {"type": "deny", "edgeDuration": 10, "edgeCountdown": 5}},
                {"type": "game-over", "message": "Demo complete"},
            ])
            conn.execute(
                """
                INSERT INTO scripts(title, description, instructor_id, created_by, visibility, tags_json, events_json, duration_seconds, difficulty, votes, plays, created_at, updated_at)
                VALUES (?, ?, ?, ?, 'public', ?, ?, ?, 'normal', 4, 0, ?, ?)
                """,
                ("Demo pacing session", "A safe, short demo script with metronome, timed events, choices, and TTS.", instructor_id, admin_id, dumps(["demo", "metronome", "beginner"]), dumps(events), compute_duration(events), now, now),
            )
            events2 = normalize_events([
                {"type": "chat-message", "text": "This template demonstrates media and device hooks without requiring hardware.", "speech": "This template demonstrates media and device hooks without requiring hardware.", "duration": 5},
                {"type": "metronome", "tempo": 72},
                {"type": "media", "url": "", "mediaType": "video", "duration": 10},
                {"type": "device", "command": {"action": "tempo", "tempo": 72}, "duration": 10},
                {"type": "stroke", "tempo": 72, "duration": 20, "grip": "normal", "style": "full"},
                {"type": "game-over", "message": "Template complete"},
            ])
            conn.execute(
                """
                INSERT INTO scripts(title, description, instructor_id, created_by, visibility, tags_json, events_json, duration_seconds, difficulty, votes, plays, created_at, updated_at)
                VALUES (?, ?, ?, ?, 'public', ?, ?, ?, 'advanced', 1, 0, ?, ?)
                """,
                ("Device and media template", "Shows how a script can cue remote media and hardware integrations.", instructor_id, admin_id, dumps(["devices", "media", "template"]), dumps(events2), compute_duration(events2), now, now),
            )
        if SEED_DEMO_DATA and conn.execute("SELECT COUNT(*) FROM game_generators").fetchone()[0] == 0:
            config = {"durationMinutes": 5, "minTempo": 45, "maxTempo": 110, "intensity": "medium", "includeEdges": True, "includeInstructions": True, "outcome": "deny"}
            conn.execute(
                "INSERT INTO game_generators(name, description, created_by, visibility, tags_json, config_json, runs, created_at, updated_at) VALUES (?, ?, ?, 'public', ?, ?, 0, ?, ?)",
                ("Quick challenge generator", "Generates a timed session from configurable tempo, duration, outcome, and option rules.", admin_id, dumps(["demo", "generator"]), dumps(config), now, now),
            )


@app.on_event("startup")
async def on_startup() -> None:
    seed_data()


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"ok": True, "name": APP_NAME, "time": utcnow()}


@app.get("/api/config")
def config() -> dict[str, Any]:
    return {
        "appName": APP_NAME,
        "allowRegistration": ALLOW_REGISTRATION,
        "eventCatalog": EVENT_CATALOG,
        "integrationsRemoteEnabled": os.getenv("ENABLE_REMOTE_INTEGRATIONS", "false").lower() == "true",
    }


# Auth
@app.post("/api/auth/register")
def register(response: Response, payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    if not ALLOW_REGISTRATION:
        raise HTTPException(403, "Registration is disabled")
    email = str(payload.get("email", "")).lower().strip()
    username = str(payload.get("username") or email.split("@")[0]).strip()[:80]
    password = str(payload.get("password", ""))
    if "@" not in email or len(password) < 8:
        raise HTTPException(400, "Valid email and password with at least 8 characters are required")
    now = utcnow()
    with db() as conn:
        exists = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
        if exists:
            raise HTTPException(409, "Email is already registered")
        count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        role = "admin" if count == 0 else "user"
        cur = conn.execute(
            "INSERT INTO users(email, username, password_hash, role, settings_json, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (email, username, hash_password(password), role, dumps({"theme": "dark", "tts": True, "metronomeAudio": True}), now, now),
        )
        user_id = cur.lastrowid
        user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    create_session(response, int(user_id))
    audit(int(user_id), "register", "user", user_id)
    return {"user": public_user(row_to_dict(user, {"settings_json"}))}


@app.post("/api/auth/login")
def login(response: Response, payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    email = str(payload.get("email", "")).lower().strip()
    password = str(payload.get("password", ""))
    with db() as conn:
        row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    if not row or not verify_password(password, row["password_hash"]):
        raise HTTPException(401, "Invalid email or password")
    create_session(response, int(row["id"]))
    user = row_to_dict(row, {"settings_json"})
    user["settings"] = user.pop("settings_json", {})
    audit(int(row["id"]), "login", "user", row["id"])
    return {"user": public_user(user)}


@app.post("/api/auth/logout")
def logout(response: Response, user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    # Cookie token removal from the browser is enough; stale DB session will expire. If you need exact session revocation,
    # add the cookie token as a dependency and delete it.
    clear_session(response)
    audit(user["id"], "logout", "user", user["id"])
    return {"ok": True}


@app.get("/api/auth/me")
def me(user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    return {"user": public_user(user)}


# Account
@app.get("/api/account/settings")
def get_account_settings(user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    return {"settings": user.get("settings") or {}}


@app.post("/api/account/settings")
def update_account_settings(payload: dict[str, Any] = Body(...), user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    settings = user.get("settings") or {}
    settings.update(payload.get("settings", payload))
    with db() as conn:
        conn.execute("UPDATE users SET settings_json = ?, username = COALESCE(?, username), updated_at = ? WHERE id = ?", (dumps(settings), payload.get("username"), utcnow(), user["id"]))
    audit(user["id"], "update-settings", "user", user["id"], {"keys": list(settings.keys())})
    return {"settings": settings}


# Instructors
@app.get("/api/instructors")
def list_instructors(user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    with db() as conn:
        rows = conn.execute("SELECT * FROM instructors WHERE is_public = 1 OR created_by = ? OR ? = 'admin' ORDER BY name", (user["id"], user["role"])).fetchall()
    return {"items": rows_to_dicts(rows)}


@app.post("/api/instructors")
def create_instructor(payload: dict[str, Any] = Body(...), user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    name = str(payload.get("name", "")).strip()
    if not name:
        raise HTTPException(400, "name is required")
    slug = slugify(payload.get("slug") or name)
    now = utcnow()
    with db() as conn:
        cur = conn.execute(
            "INSERT INTO instructors(name, slug, avatar_url, description, personality, voice, system_prompt, created_by, is_public, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (name, slug, payload.get("avatarUrl"), payload.get("description", ""), payload.get("personality", ""), payload.get("voice", "browser-default"), payload.get("systemPrompt", ""), user["id"], 1 if payload.get("isPublic", True) else 0, now, now),
        )
        row = conn.execute("SELECT * FROM instructors WHERE id = ?", (cur.lastrowid,)).fetchone()
    audit(user["id"], "create-instructor", "instructor", cur.lastrowid)
    return {"item": row_to_dict(row)}


@app.get("/api/instructors/{instructor_id}")
def get_instructor(instructor_id: int, user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    with db() as conn:
        row = conn.execute("SELECT * FROM instructors WHERE id = ?", (instructor_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Instructor not found")
    if not row["is_public"] and row["created_by"] != user["id"] and user.get("role") != "admin":
        raise HTTPException(403, "Not allowed")
    return {"item": row_to_dict(row)}


# Scripts
@app.get("/api/scripts")
def list_scripts(
    search: str = "",
    tag: str = "",
    mine: bool = False,
    cursor: int = 0,
    limit: int = Query(40, ge=1, le=100),
    user: dict[str, Any] = Depends(require_user),
) -> dict[str, Any]:
    params: list[Any] = []
    where = []
    if mine:
        where.append("s.created_by = ?")
        params.append(user["id"])
    else:
        where.append("(s.visibility = 'public' OR s.created_by = ? OR ? = 'admin')")
        params.extend([user["id"], user["role"]])
    if search:
        where.append("(LOWER(s.title) LIKE ? OR LOWER(s.description) LIKE ? OR LOWER(s.tags_json) LIKE ?)")
        q = f"%{search.lower()}%"
        params.extend([q, q, q])
    if tag:
        where.append("LOWER(s.tags_json) LIKE ?")
        params.append(f"%{tag.lower()}%")
    where_sql = " AND ".join(where) if where else "1=1"
    params.extend([limit + 1, cursor])
    with db() as conn:
        rows = conn.execute(
            f"""
            SELECT s.*, u.username AS created_by_username, i.name AS instructor_name
            FROM scripts s
            LEFT JOIN users u ON u.id = s.created_by
            LEFT JOIN instructors i ON i.id = s.instructor_id
            WHERE {where_sql}
            ORDER BY s.updated_at DESC, s.id DESC
            LIMIT ? OFFSET ?
            """,
            tuple(params),
        ).fetchall()
    has_more = len(rows) > limit
    items = [script_dict(r) for r in rows[:limit]]
    return {"items": items, "pagination": {"next": cursor + limit if has_more else None, "limit": limit}}


@app.post("/api/scripts")
def create_script(payload: dict[str, Any] = Body(...), user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    title = str(payload.get("title", "")).strip()
    if not title:
        raise HTTPException(400, "title is required")
    try:
        events = normalize_events(payload.get("events", []))
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    tags = payload.get("tags") or []
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]
    now = utcnow()
    with db() as conn:
        cur = conn.execute(
            """
            INSERT INTO scripts(title, description, instructor_id, created_by, visibility, tags_json, events_json, duration_seconds, difficulty, votes, plays, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, ?, ?)
            """,
            (title, payload.get("description", ""), payload.get("instructorId"), user["id"], payload.get("visibility", "private"), dumps(tags), dumps(events), compute_duration(events), payload.get("difficulty", "normal"), now, now),
        )
        row = conn.execute(
            """
            SELECT s.*, u.username AS created_by_username, i.name AS instructor_name
            FROM scripts s LEFT JOIN users u ON u.id = s.created_by LEFT JOIN instructors i ON i.id = s.instructor_id
            WHERE s.id = ?
            """,
            (cur.lastrowid,),
        ).fetchone()
    audit(user["id"], "create-script", "script", cur.lastrowid)
    return {"item": script_dict(row)}


@app.get("/api/scripts/{script_id}")
def get_script(script_id: int, user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    row = require_script_access(script_id, user)
    return {"item": script_dict(row)}


@app.put("/api/scripts/{script_id}")
def update_script(script_id: int, payload: dict[str, Any] = Body(...), user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    row = require_script_access(script_id, user)
    if row["created_by"] != user["id"] and user.get("role") != "admin":
        raise HTTPException(403, "Only the owner or admin can edit this script")
    current = script_dict(row)
    try:
        events = normalize_events(payload.get("events", current["events"]))
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    tags = payload.get("tags", current["tags"])
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]
    with db() as conn:
        conn.execute(
            """
            UPDATE scripts SET title=?, description=?, instructor_id=?, visibility=?, tags_json=?, events_json=?, duration_seconds=?, difficulty=?, updated_at=?
            WHERE id=?
            """,
            (payload.get("title", current["title"]), payload.get("description", current["description"]), payload.get("instructorId", current.get("instructor_id")), payload.get("visibility", current["visibility"]), dumps(tags), dumps(events), compute_duration(events), payload.get("difficulty", current["difficulty"]), utcnow(), script_id),
        )
        new_row = conn.execute(
            """
            SELECT s.*, u.username AS created_by_username, i.name AS instructor_name FROM scripts s
            LEFT JOIN users u ON u.id = s.created_by LEFT JOIN instructors i ON i.id = s.instructor_id WHERE s.id=?
            """,
            (script_id,),
        ).fetchone()
    audit(user["id"], "update-script", "script", script_id)
    return {"item": script_dict(new_row)}


@app.delete("/api/scripts/{script_id}")
def delete_script(script_id: int, user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    row = require_script_access(script_id, user)
    if row["created_by"] != user["id"] and user.get("role") != "admin":
        raise HTTPException(403, "Only the owner or admin can delete this script")
    with db() as conn:
        conn.execute("DELETE FROM scripts WHERE id = ?", (script_id,))
    audit(user["id"], "delete-script", "script", script_id)
    return {"ok": True}


@app.post("/api/scripts/{script_id}/vote")
def vote_script(script_id: int, payload: dict[str, Any] = Body(...), user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    require_script_access(script_id, user)
    vote = 1 if int(payload.get("vote", 1)) >= 0 else -1
    now = utcnow()
    with db() as conn:
        previous = conn.execute("SELECT vote FROM script_votes WHERE user_id=? AND script_id=?", (user["id"], script_id)).fetchone()
        if previous:
            conn.execute("UPDATE script_votes SET vote=?, updated_at=? WHERE user_id=? AND script_id=?", (vote, now, user["id"], script_id))
        else:
            conn.execute("INSERT INTO script_votes(user_id, script_id, vote, created_at, updated_at) VALUES (?, ?, ?, ?, ?)", (user["id"], script_id, vote, now, now))
        total = conn.execute("SELECT COALESCE(SUM(vote),0) FROM script_votes WHERE script_id=?", (script_id,)).fetchone()[0]
        conn.execute("UPDATE scripts SET votes=?, updated_at=? WHERE id=?", (total, now, script_id))
    audit(user["id"], "vote-script", "script", script_id, {"vote": vote})
    return {"votes": total}


@app.post("/api/scripts/{script_id}/play")
def record_script_play(script_id: int, user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    require_script_access(script_id, user)
    with db() as conn:
        conn.execute("UPDATE scripts SET plays = plays + 1 WHERE id = ?", (script_id,))
        plays = conn.execute("SELECT plays FROM scripts WHERE id = ?", (script_id,)).fetchone()[0]
    audit(user["id"], "play-script", "script", script_id)
    return {"plays": plays}


@app.get("/api/scripts/{script_id}/export/funscript")
def export_script_funscript(script_id: int, user: dict[str, Any] = Depends(require_user)) -> JSONResponse:
    row = require_script_access(script_id, user)
    funscript = events_to_funscript(loads(row["events_json"], []))
    return JSONResponse(funscript, headers={"Content-Disposition": f'attachment; filename="script-{script_id}.funscript"'})


# Dialog / language tools
@app.get("/api/scripts/{script_id}/dialogs")
def list_dialogs(script_id: int, user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    require_script_access(script_id, user)
    with db() as conn:
        rows = conn.execute("SELECT * FROM dialogs WHERE script_id=? ORDER BY created_at DESC", (script_id,)).fetchall()
    items = rows_to_dicts(rows, {"metadata_json"})
    return {"items": items}


@app.post("/api/dialog")
def create_dialog(payload: dict[str, Any] = Body(...), user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    script_id = int(payload.get("scriptId") or payload.get("script_id") or 0)
    row = require_script_access(script_id, user)
    instructor_id = payload.get("instructorId") or row["instructor_id"]
    style = str(payload.get("style") or "balanced")
    events = loads(row["events_json"], [])
    prompts = []
    for event in events[:25]:
        if event.get("type") in {"stroke", "wait", "instruction", "orgasm", "edge"}:
            prompts.append(event.get("title") or event.get("type"))
    with db() as conn:
        instructor = conn.execute("SELECT * FROM instructors WHERE id = ?", (instructor_id,)).fetchone() if instructor_id else None
        instructor_name = instructor["name"] if instructor else "Instructor"
        lines = [f"{instructor_name}: This {style} dialogue follows the script '{row['title']}'.", "Confirm consent and limits before starting."]
        for idx, prompt in enumerate(prompts[:12], start=1):
            lines.append(f"{idx}. Cue: {prompt}. Keep the line short, timed, and easy to follow.")
        lines.append("End with a calm reset and aftercare reminder.")
        text = "\n".join(lines)
        now = utcnow()
        cur = conn.execute(
            "INSERT INTO dialogs(script_id, instructor_id, created_by, title, text, status, metadata_json, created_at, updated_at) VALUES (?, ?, ?, ?, ?, 'ready', ?, ?, ?)",
            (script_id, instructor_id, user["id"], payload.get("title") or f"Dialogue for {row['title']}", text, dumps({"style": style, "generated": "local-template"}), now, now),
        )
        item = conn.execute("SELECT * FROM dialogs WHERE id=?", (cur.lastrowid,)).fetchone()
    audit(user["id"], "create-dialog", "dialog", cur.lastrowid, {"scriptId": script_id})
    return {"item": row_to_dict(item, {"metadata_json"})}


@app.post("/api/tools/spell-check")
def spell_check(payload: dict[str, Any] = Body(...), user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    text = str(payload.get("text", ""))
    if LANGUAGETOOL_API:
        try:
            r = requests.post(f"{LANGUAGETOOL_API}/v2/check", data={"text": text, "language": payload.get("language", "en-US")}, timeout=15)
            return {"provider": "languagetool", "result": r.json()}
        except Exception as exc:
            return {"provider": "languagetool", "error": str(exc), "matches": []}
    matches = []
    if "  " in text:
        matches.append({"message": "Double spaces detected", "shortMessage": "spacing", "offset": text.find("  "), "length": 2})
    for bad in ["teh", "recieve", "adress", "definately"]:
        idx = text.lower().find(bad)
        if idx >= 0:
            matches.append({"message": f"Possible typo: {bad}", "shortMessage": "typo", "offset": idx, "length": len(bad)})
    return {"provider": "local-basic", "matches": matches}


# Generators / games
@app.get("/api/game-generators")
def list_game_generators(search: str = "", mine: bool = False, cursor: int = 0, limit: int = Query(40, ge=1, le=100), user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    params: list[Any] = []
    where = []
    if mine:
        where.append("g.created_by = ?")
        params.append(user["id"])
    else:
        where.append("(g.visibility='public' OR g.created_by=? OR ?='admin')")
        params.extend([user["id"], user["role"]])
    if search:
        where.append("(LOWER(g.name) LIKE ? OR LOWER(g.description) LIKE ? OR LOWER(g.tags_json) LIKE ?)")
        q = f"%{search.lower()}%"
        params.extend([q, q, q])
    params.extend([limit + 1, cursor])
    with db() as conn:
        rows = conn.execute(
            f"""
            SELECT g.*, u.username AS created_by_username
            FROM game_generators g LEFT JOIN users u ON u.id=g.created_by
            WHERE {' AND '.join(where)} ORDER BY g.updated_at DESC, g.id DESC LIMIT ? OFFSET ?
            """,
            tuple(params),
        ).fetchall()
    return {"items": [generator_dict(r) for r in rows[:limit]], "pagination": {"next": cursor + limit if len(rows) > limit else None}}


@app.post("/api/game-generators")
def create_game_generator(payload: dict[str, Any] = Body(...), user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    name = str(payload.get("name", "")).strip()
    if not name:
        raise HTTPException(400, "name is required")
    tags = payload.get("tags") or []
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]
    now = utcnow()
    with db() as conn:
        cur = conn.execute(
            "INSERT INTO game_generators(name, description, created_by, visibility, tags_json, config_json, runs, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?)",
            (name, payload.get("description", ""), user["id"], payload.get("visibility", "private"), dumps(tags), dumps(payload.get("config", {})), now, now),
        )
        row = conn.execute("SELECT g.*, u.username AS created_by_username FROM game_generators g LEFT JOIN users u ON u.id=g.created_by WHERE g.id=?", (cur.lastrowid,)).fetchone()
    audit(user["id"], "create-generator", "game_generator", cur.lastrowid)
    return {"item": generator_dict(row)}


@app.get("/api/game-generators/{generator_id}")
def get_game_generator(generator_id: int, user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    with db() as conn:
        row = conn.execute("SELECT g.*, u.username AS created_by_username FROM game_generators g LEFT JOIN users u ON u.id=g.created_by WHERE g.id=?", (generator_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Generator not found")
    if row["visibility"] != "public" and row["created_by"] != user["id"] and user.get("role") != "admin":
        raise HTTPException(403, "Not allowed")
    return {"item": generator_dict(row)}


@app.put("/api/game-generators/{generator_id}")
def update_game_generator(generator_id: int, payload: dict[str, Any] = Body(...), user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    current = get_game_generator(generator_id, user)["item"]
    if current["createdBy"]["id"] != user["id"] and user.get("role") != "admin":
        raise HTTPException(403, "Only owner or admin can edit")
    tags = payload.get("tags", current["tags"])
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]
    with db() as conn:
        conn.execute(
            "UPDATE game_generators SET name=?, description=?, visibility=?, tags_json=?, config_json=?, updated_at=? WHERE id=?",
            (payload.get("name", current["name"]), payload.get("description", current["description"]), payload.get("visibility", current["visibility"]), dumps(tags), dumps(payload.get("config", current["config"])), utcnow(), generator_id),
        )
        row = conn.execute("SELECT g.*, u.username AS created_by_username FROM game_generators g LEFT JOIN users u ON u.id=g.created_by WHERE g.id=?", (generator_id,)).fetchone()
    audit(user["id"], "update-generator", "game_generator", generator_id)
    return {"item": generator_dict(row)}


@app.delete("/api/game-generators/{generator_id}")
def delete_game_generator(generator_id: int, user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    current = get_game_generator(generator_id, user)["item"]
    if current["createdBy"]["id"] != user["id"] and user.get("role") != "admin":
        raise HTTPException(403, "Only owner or admin can delete")
    with db() as conn:
        conn.execute("DELETE FROM game_generators WHERE id=?", (generator_id,))
    audit(user["id"], "delete-generator", "game_generator", generator_id)
    return {"ok": True}


@app.post("/api/game-generators/{generator_id}/start")
def start_game_generator(generator_id: int, payload: dict[str, Any] = Body(default={}), user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    generator = get_game_generator(generator_id, user)["item"]
    config = dict(generator["config"] or {})
    config.update(payload.get("config", {}))
    instructor = None
    if config.get("instructorId"):
        with db() as conn:
            instructor = row_to_dict(conn.execute("SELECT * FROM instructors WHERE id=?", (config["instructorId"],)).fetchone())
    events = generate_game_from_config(config, instructor)
    now = utcnow()
    with db() as conn:
        cur = conn.execute(
            "INSERT INTO games(title, description, generator_id, created_by, tags_json, events_json, settings_json, duration_seconds, plays, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)",
            (payload.get("title") or f"{generator['name']} run", generator["description"], generator_id, user["id"], dumps(generator["tags"]), dumps(events), dumps(config), compute_duration(events), now, now),
        )
        conn.execute("UPDATE game_generators SET runs = runs + 1, updated_at = ? WHERE id=?", (now, generator_id))
        row = conn.execute("SELECT games.*, users.username AS created_by_username FROM games LEFT JOIN users ON users.id=games.created_by WHERE games.id=?", (cur.lastrowid,)).fetchone()
    audit(user["id"], "start-generator", "game", cur.lastrowid, {"generatorId": generator_id})
    return {"item": game_dict(row)}


@app.get("/api/games")
def list_games(search: str = "", mine: bool = False, cursor: int = 0, limit: int = Query(40, ge=1, le=100), user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    params: list[Any] = []
    where = []
    if mine:
        where.append("games.created_by = ?")
        params.append(user["id"])
    else:
        where.append("(games.created_by = ? OR ? = 'admin')")
        params.extend([user["id"], user["role"]])
    if search:
        where.append("(LOWER(games.title) LIKE ? OR LOWER(games.description) LIKE ?)")
        q = f"%{search.lower()}%"
        params.extend([q, q])
    params.extend([limit + 1, cursor])
    with db() as conn:
        rows = conn.execute(
            f"SELECT games.*, users.username AS created_by_username FROM games LEFT JOIN users ON users.id=games.created_by WHERE {' AND '.join(where)} ORDER BY games.created_at DESC LIMIT ? OFFSET ?",
            tuple(params),
        ).fetchall()
    return {"items": [game_dict(r) for r in rows[:limit]], "pagination": {"next": cursor + limit if len(rows) > limit else None}}


@app.get("/api/games/{game_id}")
def get_game(game_id: int, user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    with db() as conn:
        row = conn.execute("SELECT games.*, users.username AS created_by_username FROM games LEFT JOIN users ON users.id=games.created_by WHERE games.id=?", (game_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Game not found")
    if row["created_by"] != user["id"] and user.get("role") != "admin":
        raise HTTPException(403, "Not allowed")
    return {"item": game_dict(row)}


@app.delete("/api/games/{game_id}")
def delete_game(game_id: int, user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    game = get_game(game_id, user)["item"]
    with db() as conn:
        conn.execute("DELETE FROM games WHERE id=?", (game_id,))
    audit(user["id"], "delete-game", "game", game_id)
    return {"ok": True}


@app.post("/api/games/{game_id}/play")
def record_game_play(game_id: int, user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    get_game(game_id, user)
    with db() as conn:
        conn.execute("UPDATE games SET plays = plays + 1 WHERE id = ?", (game_id,))
        plays = conn.execute("SELECT plays FROM games WHERE id = ?", (game_id,)).fetchone()[0]
    audit(user["id"], "play-game", "game", game_id)
    return {"plays": plays}


# Media
@app.get("/api/media")
def list_media(search: str = "", media_type: str = "", user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    params: list[Any] = [user["id"], user["role"]]
    where = ["(media.created_by = ? OR ? = 'admin' OR media.source='seed')"]
    if search:
        where.append("(LOWER(media.title) LIKE ? OR LOWER(media.tags_json) LIKE ?)")
        q = f"%{search.lower()}%"
        params.extend([q, q])
    if media_type:
        where.append("media.media_type = ?")
        params.append(media_type)
    with db() as conn:
        rows = conn.execute(
            f"SELECT media.*, users.username AS created_by_username FROM media LEFT JOIN users ON users.id=media.created_by WHERE {' AND '.join(where)} ORDER BY media.created_at DESC",
            tuple(params),
        ).fetchall()
    return {"items": [media_dict(r) for r in rows]}


@app.post("/api/media")
def create_media(payload: dict[str, Any] = Body(...), user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    title = str(payload.get("title", "")).strip()
    url = str(payload.get("url", "")).strip()
    media_type = str(payload.get("mediaType") or payload.get("media_type") or "video").strip()
    if not title or not url:
        raise HTTPException(400, "title and url are required")
    tags = payload.get("tags") or []
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]
    now = utcnow()
    with db() as conn:
        cur = conn.execute(
            "INSERT INTO media(title, media_type, url, source, created_by, tags_json, metadata_json, created_at, updated_at) VALUES (?, ?, ?, 'url', ?, ?, ?, ?, ?)",
            (title, media_type, url, user["id"], dumps(tags), dumps(payload.get("metadata", {})), now, now),
        )
        row = conn.execute("SELECT media.*, users.username AS created_by_username FROM media LEFT JOIN users ON users.id=media.created_by WHERE media.id=?", (cur.lastrowid,)).fetchone()
    audit(user["id"], "create-media", "media", cur.lastrowid)
    return {"item": media_dict(row)}


@app.post("/api/media/upload")
def upload_media(title: str = Form(...), mediaType: str = Form("video"), tags: str = Form(""), file: UploadFile = File(...), user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    safe_name = secrets.token_hex(8) + "-" + Path(file.filename or "upload.bin").name.replace("/", "_")
    dest = UPLOAD_DIR / safe_name
    with dest.open("wb") as fh:
        shutil.copyfileobj(file.file, fh)
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    url = f"/uploads/{safe_name}"
    now = utcnow()
    with db() as conn:
        cur = conn.execute(
            "INSERT INTO media(title, media_type, url, source, created_by, tags_json, metadata_json, created_at, updated_at) VALUES (?, ?, ?, 'upload', ?, ?, ?, ?, ?)",
            (title, mediaType, url, user["id"], dumps(tag_list), dumps({"filename": file.filename, "contentType": file.content_type}), now, now),
        )
        row = conn.execute("SELECT media.*, users.username AS created_by_username FROM media LEFT JOIN users ON users.id=media.created_by WHERE media.id=?", (cur.lastrowid,)).fetchone()
    audit(user["id"], "upload-media", "media", cur.lastrowid)
    return {"item": media_dict(row)}


@app.delete("/api/media/{media_id}")
def delete_media(media_id: int, user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    with db() as conn:
        row = conn.execute("SELECT * FROM media WHERE id=?", (media_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Media not found")
        if row["created_by"] != user["id"] and user.get("role") != "admin":
            raise HTTPException(403, "Not allowed")
        conn.execute("DELETE FROM media WHERE id=?", (media_id,))
    audit(user["id"], "delete-media", "media", media_id)
    return {"ok": True}


@app.get("/uploads/{file_name:path}")
def uploaded_file(file_name: str, user: dict[str, Any] = Depends(require_user)) -> FileResponse:
    path = (UPLOAD_DIR / file_name).resolve()
    if not str(path).startswith(str(UPLOAD_DIR.resolve())) or not path.exists():
        raise HTTPException(404, "File not found")
    return FileResponse(path)


# Devices
@app.get("/api/devices")
def list_devices(user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    with db() as conn:
        rows = conn.execute("SELECT * FROM devices WHERE user_id=? ORDER BY updated_at DESC", (user["id"],)).fetchall()
    return {"items": [device_dict(r) for r in rows]}


@app.post("/api/devices")
def create_device(payload: dict[str, Any] = Body(...), user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    device_type = str(payload.get("deviceType") or payload.get("device_type") or "mock").lower()
    label = str(payload.get("label") or device_type.title()).strip()
    config = payload.get("config") or {}
    now = utcnow()
    with db() as conn:
        cur = conn.execute(
            "INSERT INTO devices(user_id, device_type, label, config_json, status, created_at, updated_at) VALUES (?, ?, ?, ?, 'unknown', ?, ?)",
            (user["id"], device_type, label, dumps(config), now, now),
        )
        row = conn.execute("SELECT * FROM devices WHERE id=?", (cur.lastrowid,)).fetchone()
    audit(user["id"], "create-device", "device", cur.lastrowid, {"type": device_type})
    return {"item": device_dict(row)}


@app.put("/api/devices/{device_id}")
def update_device(device_id: int, payload: dict[str, Any] = Body(...), user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    with db() as conn:
        row = conn.execute("SELECT * FROM devices WHERE id=? AND user_id=?", (device_id, user["id"])).fetchone()
        if not row:
            raise HTTPException(404, "Device not found")
        config = payload.get("config", loads(row["config_json"], {}))
        conn.execute("UPDATE devices SET label=?, config_json=?, updated_at=? WHERE id=?", (payload.get("label", row["label"]), dumps(config), utcnow(), device_id))
        new_row = conn.execute("SELECT * FROM devices WHERE id=?", (device_id,)).fetchone()
    audit(user["id"], "update-device", "device", device_id)
    return {"item": device_dict(new_row)}


@app.delete("/api/devices/{device_id}")
def delete_device(device_id: int, user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    with db() as conn:
        row = conn.execute("SELECT * FROM devices WHERE id=? AND user_id=?", (device_id, user["id"])).fetchone()
        if not row:
            raise HTTPException(404, "Device not found")
        conn.execute("DELETE FROM devices WHERE id=?", (device_id,))
    audit(user["id"], "delete-device", "device", device_id)
    return {"ok": True}


@app.post("/api/devices/{device_id}/test")
def device_test(device_id: int, user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    with db() as conn:
        row = conn.execute("SELECT * FROM devices WHERE id=? AND user_id=?", (device_id, user["id"])).fetchone()
        if not row:
            raise HTTPException(404, "Device not found")
        response = test_device(row["device_type"], loads(row["config_json"], {}))
        status_text = "connected" if response.get("ok") else "error"
        conn.execute("UPDATE devices SET status=?, last_seen_at=?, updated_at=? WHERE id=?", (status_text, utcnow() if response.get("ok") else row["last_seen_at"], utcnow(), device_id))
        conn.execute("INSERT INTO device_command_logs(device_id, user_id, command_json, response_json, status, created_at) VALUES (?, ?, ?, ?, ?, ?)", (device_id, user["id"], dumps({"action": "test"}), dumps(response), status_text, utcnow()))
    return {"status": status_text, "response": response}


@app.post("/api/devices/{device_id}/command")
def device_command(device_id: int, payload: dict[str, Any] = Body(...), user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    command = payload.get("command", payload)
    with db() as conn:
        row = conn.execute("SELECT * FROM devices WHERE id=? AND user_id=?", (device_id, user["id"])).fetchone()
        if not row:
            raise HTTPException(404, "Device not found")
        response = send_device_command(row["device_type"], loads(row["config_json"], {}), command)
        status_text = "sent" if response.get("ok") else "error"
        conn.execute("INSERT INTO device_command_logs(device_id, user_id, command_json, response_json, status, created_at) VALUES (?, ?, ?, ?, ?, ?)", (device_id, user["id"], dumps(command), dumps(response), status_text, utcnow()))
        if response.get("ok"):
            conn.execute("UPDATE devices SET status='connected', last_seen_at=?, updated_at=? WHERE id=?", (utcnow(), utcnow(), device_id))
    return {"status": status_text, "response": response}


@app.post("/api/devices/{device_id}/upload-script/{script_id}")
def upload_script_to_device(device_id: int, script_id: int, user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    script = script_dict(require_script_access(script_id, user))
    with db() as conn:
        row = conn.execute("SELECT * FROM devices WHERE id=? AND user_id=?", (device_id, user["id"])).fetchone()
        if not row:
            raise HTTPException(404, "Device not found")
        if row["device_type"] != "handy":
            raise HTTPException(400, "Script upload is currently implemented for The Handy devices")
        funscript = events_to_funscript(script["events"])
        response = upload_handy_script(loads(row["config_json"], {}), funscript)
        conn.execute("INSERT INTO device_command_logs(device_id, user_id, command_json, response_json, status, created_at) VALUES (?, ?, ?, ?, ?, ?)", (device_id, user["id"], dumps({"action": "upload-script", "scriptId": script_id}), dumps(response), "sent" if response.get("ok") else "error", utcnow()))
    return {"response": response, "funscriptSummary": {"actions": len(funscript.get("actions", []))}}


# Challenger websocket rooms
class RoomManager:
    def __init__(self) -> None:
        self.rooms: dict[str, dict[str, Any]] = {}
        self.connections: dict[str, list[WebSocket]] = {}

    async def connect(self, code: str, websocket: WebSocket, user: dict[str, Any]) -> None:
        await websocket.accept()
        self.connections.setdefault(code, []).append(websocket)
        self.rooms.setdefault(code, {"players": {}, "state": "waiting", "events": [], "chat": []})
        self.rooms[code]["players"][str(user["id"])] = {"id": user["id"], "username": user["username"], "joinedAt": utcnow()}
        await self.broadcast(code, {"type": "presence", "room": self.rooms[code]})

    def disconnect(self, code: str, websocket: WebSocket, user: dict[str, Any] | None = None) -> None:
        try:
            self.connections.get(code, []).remove(websocket)
        except ValueError:
            pass
        if user and code in self.rooms:
            self.rooms[code].get("players", {}).pop(str(user["id"]), None)

    async def broadcast(self, code: str, message: dict[str, Any]) -> None:
        stale = []
        for ws in self.connections.get(code, []):
            try:
                await ws.send_json(message)
            except Exception:
                stale.append(ws)
        for ws in stale:
            self.disconnect(code, ws)


rooms = RoomManager()


@app.post("/api/challenger/rooms")
def create_room(payload: dict[str, Any] = Body(default={}), user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    code = secrets.token_hex(3).upper()
    title = payload.get("title") or f"{user['username']}'s room"
    snapshot = {"players": {}, "state": "waiting", "events": [], "chat": []}
    now = utcnow()
    with db() as conn:
        conn.execute("INSERT INTO challenger_rooms(code, title, status, created_by, config_json, snapshot_json, created_at, updated_at) VALUES (?, ?, 'waiting', ?, ?, ?, ?, ?)", (code, title, user["id"], dumps(payload.get("config", {})), dumps(snapshot), now, now))
    audit(user["id"], "create-room", "challenger_room", code)
    return {"item": {"code": code, "title": title, "status": "waiting", "snapshot": snapshot}}


@app.get("/api/challenger/rooms/{code}")
def get_room(code: str, user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    code = code.upper()
    with db() as conn:
        row = conn.execute("SELECT * FROM challenger_rooms WHERE code=?", (code,)).fetchone()
    if not row:
        raise HTTPException(404, "Room not found")
    snapshot = rooms.rooms.get(code) or loads(row["snapshot_json"], {})
    return {"item": {"code": row["code"], "title": row["title"], "status": row["status"], "config": loads(row["config_json"], {}), "snapshot": snapshot}}


@app.get("/api/challenger/stats")
def challenger_stats(user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    with db() as conn:
        total_rooms = conn.execute("SELECT COUNT(*) FROM challenger_rooms").fetchone()[0]
        games = conn.execute("SELECT COUNT(*) FROM games").fetchone()[0]
    return {"activeRooms": len(rooms.connections), "totalRooms": total_rooms, "generatedGames": games, "livePlayers": sum(len(v) for v in rooms.connections.values())}


@app.websocket("/ws/challenger/{code}")
async def challenger_ws(websocket: WebSocket, code: str) -> None:
    user = await websocket_user(websocket)
    if not user:
        await websocket.close(code=4401)
        return
    code = code.upper()
    await rooms.connect(code, websocket, user)
    try:
        while True:
            message = await websocket.receive_json()
            typ = message.get("type")
            room = rooms.rooms.setdefault(code, {"players": {}, "state": "waiting", "events": [], "chat": []})
            if typ == "chat":
                chat = {"user": user["username"], "text": str(message.get("text", ""))[:500], "at": utcnow()}
                room.setdefault("chat", []).append(chat)
                await rooms.broadcast(code, {"type": "chat", "message": chat})
            elif typ == "state":
                room["state"] = message.get("state", room.get("state"))
                room["position"] = message.get("position", room.get("position", 0))
                await rooms.broadcast(code, {"type": "state", "room": room})
            elif typ == "event":
                event = message.get("event", {})
                event["by"] = user["username"]
                event["at"] = utcnow()
                room.setdefault("events", []).append(event)
                await rooms.broadcast(code, {"type": "event", "event": event})
            else:
                await websocket.send_json({"type": "error", "message": "Unknown message type"})
    except WebSocketDisconnect:
        rooms.disconnect(code, websocket, user)
        await rooms.broadcast(code, {"type": "presence", "room": rooms.rooms.get(code, {})})


# Admin
@app.get("/api/admin/stats")
def admin_stats(user: dict[str, Any] = Depends(require_admin)) -> dict[str, Any]:
    with db() as conn:
        tables = ["users", "scripts", "game_generators", "games", "media", "devices", "challenger_rooms", "dialogs"]
        counts = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in tables}
        recent = rows_to_dicts(conn.execute("SELECT * FROM audit_log ORDER BY created_at DESC LIMIT 50").fetchall(), {"metadata_json"})
    return {"counts": counts, "activeWsRooms": len(rooms.connections), "recentAudit": recent}


@app.get("/api/admin/users")
def admin_users(user: dict[str, Any] = Depends(require_admin)) -> dict[str, Any]:
    with db() as conn:
        rows = conn.execute("SELECT id, email, username, role, created_at, updated_at FROM users ORDER BY id").fetchall()
    return {"items": rows_to_dicts(rows)}


@app.put("/api/admin/users/{user_id}")
def admin_update_user(user_id: int, payload: dict[str, Any] = Body(...), user: dict[str, Any] = Depends(require_admin)) -> dict[str, Any]:
    with db() as conn:
        conn.execute("UPDATE users SET role=COALESCE(?, role), updated_at=? WHERE id=?", (payload.get("role"), utcnow(), user_id))
        row = conn.execute("SELECT id, email, username, role, created_at, updated_at FROM users WHERE id=?", (user_id,)).fetchone()
    if not row:
        raise HTTPException(404, "User not found")
    audit(user["id"], "admin-update-user", "user", user_id, payload)
    return {"item": row_to_dict(row)}


@app.get("/api/admin/instruction/generate/status")
def queue_status(user: dict[str, Any] = Depends(require_admin)) -> dict[str, Any]:
    # Local build uses immediate template generation. This mirrors the production queue-status surface.
    return {"status": "idle", "queued": 0, "processing": 0, "failed": 0, "provider": "local-template"}


@app.post("/api/admin/instruction/generate/rejected/reprocess")
def queue_reprocess(user: dict[str, Any] = Depends(require_admin)) -> dict[str, Any]:
    audit(user["id"], "reprocess-queue", "queue", "dialogue")
    return {"ok": True, "message": "No rejected local jobs to reprocess."}


@app.get("/api/admin/challenger/live")
def admin_challenger_live(user: dict[str, Any] = Depends(require_admin)) -> dict[str, Any]:
    return {"rooms": {code: {"connections": len(conns), "snapshot": rooms.rooms.get(code, {})} for code, conns in rooms.connections.items()}}


# Legal text surfaces
@app.get("/api/legal/{document}")
def legal(document: str) -> dict[str, Any]:
    docs = {
        "terms": "Self-hosted personal-use software. You are responsible for lawful content, consent, safety, and third-party device credentials.",
        "privacy": "This Docker build stores account, script, media metadata, and device settings in your local SQLite database/volume. No payment data is collected by this app.",
    }
    if document not in docs:
        raise HTTPException(404, "Document not found")
    return {"document": document, "title": document.replace("-", " ").title(), "body": docs[document]}


@app.get("/robots.txt", response_class=PlainTextResponse)
def robots() -> str:
    return "User-agent: *\nDisallow: /\n"


@app.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
def unknown_api(path: str) -> JSONResponse:
    return JSONResponse({"detail": "API endpoint not found"}, status_code=404)


@app.get("/{path:path}")
def spa(path: str = "") -> FileResponse:
    index = STATIC_DIR / "index.html"
    return FileResponse(index)
