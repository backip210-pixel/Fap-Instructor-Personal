from __future__ import annotations

import os
import secrets
import shutil
from pathlib import Path
from typing import Any

import requests
from fastapi import Body, FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from .database import UPLOAD_DIR, db, dumps, init_db, loads, row_to_dict, rows_to_dicts, utcnow
from .game import EVENT_CATALOG, compute_duration, events_to_funscript, generate_game_from_config, normalize_events
from .integrations import send_device_command, test_device, upload_handy_script

APP_NAME = os.getenv("APP_NAME", "Fap Instructor Personal")
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "http://localhost:8080")
SEED_DEMO_DATA = os.getenv("SEED_DEMO_DATA", "true").lower() == "true"
LANGUAGETOOL_API = os.getenv("LANGUAGETOOL_API", "").rstrip("/")

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(title=APP_NAME, version="2.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[PUBLIC_BASE_URL, "http://localhost:8080", "http://127.0.0.1:8080", "*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def _tags(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if isinstance(value, str):
        return [v.strip() for v in value.split(",") if v.strip()]
    return []


def script_dict(row: Any) -> dict[str, Any]:
    d = dict(row)
    d["tags"] = loads(d.pop("tags_json", "[]"), [])
    d["events"] = loads(d.pop("events_json", "[]"), [])
    d["durationSeconds"] = d.pop("duration_seconds", 0)
    d["createdAt"] = d.pop("created_at", None)
    d["updatedAt"] = d.pop("updated_at", None)
    for unused in ["created_by", "created_by_username", "instructor_id", "instructor_name", "visibility", "required_subscription"]:
        d.pop(unused, None)
    return d


def generator_dict(row: Any) -> dict[str, Any]:
    d = dict(row)
    d["tags"] = loads(d.pop("tags_json", "[]"), [])
    d["config"] = loads(d.pop("config_json", "{}"), {})
    d["createdAt"] = d.pop("created_at", None)
    d["updatedAt"] = d.pop("updated_at", None)
    for unused in ["created_by", "visibility", "created_by_username"]:
        d.pop(unused, None)
    return d


def game_dict(row: Any) -> dict[str, Any]:
    d = dict(row)
    d["tags"] = loads(d.pop("tags_json", "[]"), [])
    d["events"] = loads(d.pop("events_json", "[]"), [])
    d["settings"] = loads(d.pop("settings_json", "{}"), {})
    d["durationSeconds"] = d.pop("duration_seconds", 0)
    d["createdAt"] = d.pop("created_at", None)
    d["updatedAt"] = d.pop("updated_at", None)
    d.pop("created_by", None)
    return d


def media_dict(row: Any) -> dict[str, Any]:
    d = dict(row)
    d["tags"] = loads(d.pop("tags_json", "[]"), [])
    d["metadata"] = loads(d.pop("metadata_json", "{}"), {})
    d["mediaType"] = d.pop("media_type", "")
    d["createdAt"] = d.pop("created_at", None)
    d["updatedAt"] = d.pop("updated_at", None)
    d.pop("created_by", None)
    return d


def device_dict(row: Any) -> dict[str, Any]:
    d = dict(row)
    d["deviceType"] = d.pop("device_type", "")
    d["config"] = loads(d.pop("config_json", "{}"), {})
    d["lastSeenAt"] = d.pop("last_seen_at", None)
    d["createdAt"] = d.pop("created_at", None)
    d["updatedAt"] = d.pop("updated_at", None)
    d.pop("user_id", None)
    return d


def get_script_row(script_id: int) -> Any:
    with db() as conn:
        row = conn.execute("SELECT * FROM scripts WHERE id=?", (script_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Script not found")
    return row


def seed_data() -> None:
    init_db()
    if not SEED_DEMO_DATA:
        return
    now = utcnow()
    with db() as conn:
        if conn.execute("SELECT COUNT(*) FROM scripts").fetchone()[0] == 0:
            events = normalize_events([
                {"type": "chat-message", "text": "Welcome. Press start and follow the timer.", "speech": "Welcome. Press start and follow the timer.", "duration": 4},
                {"type": "metronome", "tempo": 60, "measure": "4/4"},
                {"type": "stroke", "tempo": 60, "duration": 20, "grip": "light", "style": "full"},
                {"type": "wait", "duration": 8},
                {"type": "stroke", "tempo": 90, "duration": 24, "grip": "normal", "style": "short"},
                {"type": "instruction", "title": "Check in", "description": "Slow down, pause, or continue.", "duration": 6, "options": [{"title": "Continue", "events": []}, {"title": "Slow down", "events": [{"type": "stroke-tempo", "tempo": 50}]}]},
                {"type": "stroke", "tempo": 110, "duration": 18, "grip": "normal", "style": "full"},
                {"type": "orgasm", "orgasm": {"type": "deny", "edgeDuration": 10, "edgeCountdown": 5}},
                {"type": "game-over", "message": "Demo complete"},
            ])
            conn.execute(
                """
                INSERT INTO scripts(title, description, tags_json, events_json, duration_seconds, difficulty, votes, plays, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                ("Demo pacing session", "A short demo script with metronome, timed events, choices, and TTS.", dumps(["demo", "metronome"]), dumps(events), compute_duration(events), "normal", 3, 0, now, now),
            )
            events2 = normalize_events([
                {"type": "chat-message", "text": "This template demonstrates media and device hooks without requiring hardware.", "duration": 5},
                {"type": "metronome", "tempo": 72},
                {"type": "media", "url": "", "mediaType": "video", "duration": 10},
                {"type": "device", "command": {"action": "tempo", "tempo": 72}, "duration": 10},
                {"type": "stroke", "tempo": 72, "duration": 20, "grip": "normal", "style": "full"},
                {"type": "game-over", "message": "Template complete"},
            ])
            conn.execute(
                """
                INSERT INTO scripts(title, description, tags_json, events_json, duration_seconds, difficulty, votes, plays, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                ("Device and media template", "Shows how a script can cue media and hardware integrations.", dumps(["devices", "media"]), dumps(events2), compute_duration(events2), "advanced", 1, 0, now, now),
            )
        if conn.execute("SELECT COUNT(*) FROM game_generators").fetchone()[0] == 0:
            config = {"durationMinutes": 5, "minTempo": 45, "maxTempo": 110, "intensity": "medium", "includeEdges": True, "includeInstructions": True, "outcome": "deny"}
            conn.execute(
                "INSERT INTO game_generators(name, description, tags_json, config_json, runs, created_at, updated_at) VALUES (?, ?, ?, ?, 0, ?, ?)",
                ("Quick challenge generator", "Generate a timed session from tempo, duration, outcome, and check-in rules.", dumps(["demo", "generator"]), dumps(config), now, now),
            )


@app.on_event("startup")
async def on_startup() -> None:
    seed_data()


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"ok": True, "name": APP_NAME, "time": utcnow(), "mode": "simple-no-login"}


@app.get("/api/config")
def config() -> dict[str, Any]:
    return {
        "appName": APP_NAME,
        "eventCatalog": EVENT_CATALOG,
        "integrationsRemoteEnabled": os.getenv("ENABLE_REMOTE_INTEGRATIONS", "false").lower() == "true",
    }


@app.get("/api/scripts")
def list_scripts(search: str = "", tag: str = "", cursor: int = 0, limit: int = Query(50, ge=1, le=200)) -> dict[str, Any]:
    params: list[Any] = []
    where = []
    if search:
        where.append("(LOWER(title) LIKE ? OR LOWER(description) LIKE ? OR LOWER(tags_json) LIKE ?)")
        q = f"%{search.lower()}%"
        params.extend([q, q, q])
    if tag:
        where.append("LOWER(tags_json) LIKE ?")
        params.append(f"%{tag.lower()}%")
    params.extend([limit + 1, cursor])
    sql = f"SELECT * FROM scripts WHERE {' AND '.join(where) if where else '1=1'} ORDER BY updated_at DESC, id DESC LIMIT ? OFFSET ?"
    with db() as conn:
        rows = conn.execute(sql, tuple(params)).fetchall()
    return {"items": [script_dict(r) for r in rows[:limit]], "pagination": {"next": cursor + limit if len(rows) > limit else None}}


@app.post("/api/scripts")
def create_script(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    title = str(payload.get("title", "")).strip()
    if not title:
        raise HTTPException(400, "title is required")
    try:
        events = normalize_events(payload.get("events", []))
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    now = utcnow()
    with db() as conn:
        cur = conn.execute(
            """
            INSERT INTO scripts(title, description, tags_json, events_json, duration_seconds, difficulty, votes, plays, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, 0, 0, ?, ?)
            """,
            (title, payload.get("description", ""), dumps(_tags(payload.get("tags"))), dumps(events), compute_duration(events), payload.get("difficulty", "normal"), now, now),
        )
        row = conn.execute("SELECT * FROM scripts WHERE id=?", (cur.lastrowid,)).fetchone()
    return {"item": script_dict(row)}


@app.get("/api/scripts/{script_id}")
def get_script(script_id: int) -> dict[str, Any]:
    return {"item": script_dict(get_script_row(script_id))}


@app.put("/api/scripts/{script_id}")
def update_script(script_id: int, payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    current = script_dict(get_script_row(script_id))
    try:
        events = normalize_events(payload.get("events", current["events"]))
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    now = utcnow()
    with db() as conn:
        conn.execute(
            """
            UPDATE scripts SET title=?, description=?, tags_json=?, events_json=?, duration_seconds=?, difficulty=?, updated_at=? WHERE id=?
            """,
            (payload.get("title", current["title"]), payload.get("description", current.get("description", "")), dumps(_tags(payload.get("tags", current["tags"]))), dumps(events), compute_duration(events), payload.get("difficulty", current.get("difficulty", "normal")), now, script_id),
        )
        row = conn.execute("SELECT * FROM scripts WHERE id=?", (script_id,)).fetchone()
    return {"item": script_dict(row)}


@app.delete("/api/scripts/{script_id}")
def delete_script(script_id: int) -> dict[str, Any]:
    get_script_row(script_id)
    with db() as conn:
        conn.execute("DELETE FROM scripts WHERE id=?", (script_id,))
    return {"ok": True}


@app.post("/api/scripts/{script_id}/vote")
def vote_script(script_id: int, payload: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    get_script_row(script_id)
    vote = 1 if int(payload.get("vote", 1)) >= 0 else -1
    with db() as conn:
        conn.execute("UPDATE scripts SET votes=votes+?, updated_at=? WHERE id=?", (vote, utcnow(), script_id))
        votes = conn.execute("SELECT votes FROM scripts WHERE id=?", (script_id,)).fetchone()[0]
    return {"votes": votes}


@app.post("/api/scripts/{script_id}/play")
def record_script_play(script_id: int) -> dict[str, Any]:
    get_script_row(script_id)
    with db() as conn:
        conn.execute("UPDATE scripts SET plays=plays+1 WHERE id=?", (script_id,))
        plays = conn.execute("SELECT plays FROM scripts WHERE id=?", (script_id,)).fetchone()[0]
    return {"plays": plays}


@app.get("/api/scripts/{script_id}/export/funscript")
def export_script_funscript(script_id: int) -> JSONResponse:
    row = get_script_row(script_id)
    return JSONResponse(events_to_funscript(loads(row["events_json"], [])), headers={"Content-Disposition": f'attachment; filename="script-{script_id}.funscript"'})


@app.post("/api/dialog")
def create_dialog(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    script_id = int(payload.get("scriptId") or 0)
    script = script_dict(get_script_row(script_id))
    lines = [f"Dialogue notes for '{script['title']}'", "Use short, timed, easy-to-follow lines."]
    for idx, event in enumerate(script["events"][:12], 1):
        lines.append(f"{idx}. Cue: {event.get('title') or event.get('type')}")
    return {"item": {"title": f"Dialogue for {script['title']}", "text": "\n".join(lines), "status": "ready"}}


@app.post("/api/tools/spell-check")
def spell_check(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    text = str(payload.get("text", ""))
    if LANGUAGETOOL_API:
        try:
            r = requests.post(f"{LANGUAGETOOL_API}/v2/check", data={"text": text, "language": payload.get("language", "en-US")}, timeout=15)
            return {"provider": "languagetool", "result": r.json()}
        except Exception as exc:
            return {"provider": "languagetool", "error": str(exc), "matches": []}
    return {"provider": "local-basic", "matches": []}


@app.get("/api/game-generators")
def list_game_generators(search: str = "", cursor: int = 0, limit: int = Query(50, ge=1, le=200)) -> dict[str, Any]:
    params: list[Any] = []
    where = []
    if search:
        where.append("(LOWER(name) LIKE ? OR LOWER(description) LIKE ? OR LOWER(tags_json) LIKE ?)")
        q = f"%{search.lower()}%"
        params.extend([q, q, q])
    params.extend([limit + 1, cursor])
    sql = f"SELECT * FROM game_generators WHERE {' AND '.join(where) if where else '1=1'} ORDER BY updated_at DESC, id DESC LIMIT ? OFFSET ?"
    with db() as conn:
        rows = conn.execute(sql, tuple(params)).fetchall()
    return {"items": [generator_dict(r) for r in rows[:limit]], "pagination": {"next": cursor + limit if len(rows) > limit else None}}


@app.post("/api/game-generators")
def create_game_generator(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    name = str(payload.get("name", "")).strip()
    if not name:
        raise HTTPException(400, "name is required")
    now = utcnow()
    with db() as conn:
        cur = conn.execute(
            "INSERT INTO game_generators(name, description, tags_json, config_json, runs, created_at, updated_at) VALUES (?, ?, ?, ?, 0, ?, ?)",
            (name, payload.get("description", ""), dumps(_tags(payload.get("tags"))), dumps(payload.get("config", {})), now, now),
        )
        row = conn.execute("SELECT * FROM game_generators WHERE id=?", (cur.lastrowid,)).fetchone()
    return {"item": generator_dict(row)}


@app.get("/api/game-generators/{generator_id}")
def get_game_generator(generator_id: int) -> dict[str, Any]:
    with db() as conn:
        row = conn.execute("SELECT * FROM game_generators WHERE id=?", (generator_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Generator not found")
    return {"item": generator_dict(row)}


@app.put("/api/game-generators/{generator_id}")
def update_game_generator(generator_id: int, payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    current = get_game_generator(generator_id)["item"]
    now = utcnow()
    with db() as conn:
        conn.execute(
            "UPDATE game_generators SET name=?, description=?, tags_json=?, config_json=?, updated_at=? WHERE id=?",
            (payload.get("name", current["name"]), payload.get("description", current.get("description", "")), dumps(_tags(payload.get("tags", current["tags"]))), dumps(payload.get("config", current["config"])), now, generator_id),
        )
        row = conn.execute("SELECT * FROM game_generators WHERE id=?", (generator_id,)).fetchone()
    return {"item": generator_dict(row)}


@app.delete("/api/game-generators/{generator_id}")
def delete_game_generator(generator_id: int) -> dict[str, Any]:
    get_game_generator(generator_id)
    with db() as conn:
        conn.execute("DELETE FROM game_generators WHERE id=?", (generator_id,))
    return {"ok": True}


@app.post("/api/game-generators/{generator_id}/start")
def start_game_generator(generator_id: int, payload: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    generator = get_game_generator(generator_id)["item"]
    config = dict(generator.get("config") or {})
    config.update(payload.get("config", {}))
    events = generate_game_from_config(config)
    now = utcnow()
    with db() as conn:
        cur = conn.execute(
            "INSERT INTO games(title, description, generator_id, tags_json, events_json, settings_json, duration_seconds, plays, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, ?)",
            (payload.get("title") or f"{generator['name']} run", generator.get("description", ""), generator_id, dumps(generator.get("tags", [])), dumps(events), dumps(config), compute_duration(events), now, now),
        )
        conn.execute("UPDATE game_generators SET runs=runs+1, updated_at=? WHERE id=?", (now, generator_id))
        row = conn.execute("SELECT * FROM games WHERE id=?", (cur.lastrowid,)).fetchone()
    return {"item": game_dict(row)}


@app.get("/api/games")
def list_games(search: str = "", cursor: int = 0, limit: int = Query(50, ge=1, le=200)) -> dict[str, Any]:
    params: list[Any] = []
    where = []
    if search:
        where.append("(LOWER(title) LIKE ? OR LOWER(description) LIKE ? OR LOWER(tags_json) LIKE ?)")
        q = f"%{search.lower()}%"
        params.extend([q, q, q])
    params.extend([limit + 1, cursor])
    sql = f"SELECT * FROM games WHERE {' AND '.join(where) if where else '1=1'} ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?"
    with db() as conn:
        rows = conn.execute(sql, tuple(params)).fetchall()
    return {"items": [game_dict(r) for r in rows[:limit]], "pagination": {"next": cursor + limit if len(rows) > limit else None}}


@app.get("/api/games/{game_id}")
def get_game(game_id: int) -> dict[str, Any]:
    with db() as conn:
        row = conn.execute("SELECT * FROM games WHERE id=?", (game_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Game not found")
    return {"item": game_dict(row)}


@app.delete("/api/games/{game_id}")
def delete_game(game_id: int) -> dict[str, Any]:
    get_game(game_id)
    with db() as conn:
        conn.execute("DELETE FROM games WHERE id=?", (game_id,))
    return {"ok": True}


@app.post("/api/games/{game_id}/play")
def record_game_play(game_id: int) -> dict[str, Any]:
    get_game(game_id)
    with db() as conn:
        conn.execute("UPDATE games SET plays=plays+1 WHERE id=?", (game_id,))
        plays = conn.execute("SELECT plays FROM games WHERE id=?", (game_id,)).fetchone()[0]
    return {"plays": plays}


@app.get("/api/media")
def list_media(search: str = "", media_type: str = "") -> dict[str, Any]:
    params: list[Any] = []
    where = []
    if search:
        where.append("(LOWER(title) LIKE ? OR LOWER(tags_json) LIKE ?)")
        q = f"%{search.lower()}%"
        params.extend([q, q])
    if media_type:
        where.append("media_type=?")
        params.append(media_type)
    sql = f"SELECT * FROM media WHERE {' AND '.join(where) if where else '1=1'} ORDER BY created_at DESC, id DESC"
    with db() as conn:
        rows = conn.execute(sql, tuple(params)).fetchall()
    return {"items": [media_dict(r) for r in rows]}


@app.post("/api/media")
def create_media(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    title = str(payload.get("title", "")).strip()
    url = str(payload.get("url", "")).strip()
    media_type = str(payload.get("mediaType") or payload.get("media_type") or "video")
    if not title or not url:
        raise HTTPException(400, "title and url are required")
    now = utcnow()
    with db() as conn:
        cur = conn.execute(
            "INSERT INTO media(title, media_type, url, source, tags_json, metadata_json, created_at, updated_at) VALUES (?, ?, ?, 'url', ?, ?, ?, ?)",
            (title, media_type, url, dumps(_tags(payload.get("tags"))), dumps(payload.get("metadata", {})), now, now),
        )
        row = conn.execute("SELECT * FROM media WHERE id=?", (cur.lastrowid,)).fetchone()
    return {"item": media_dict(row)}


@app.post("/api/media/upload")
def upload_media(title: str = Form(...), mediaType: str = Form("video"), tags: str = Form(""), file: UploadFile = File(...)) -> dict[str, Any]:
    safe_name = secrets.token_hex(8) + "-" + Path(file.filename or "upload.bin").name.replace("/", "_")
    dest = UPLOAD_DIR / safe_name
    with dest.open("wb") as fh:
        shutil.copyfileobj(file.file, fh)
    now = utcnow()
    with db() as conn:
        cur = conn.execute(
            "INSERT INTO media(title, media_type, url, source, tags_json, metadata_json, created_at, updated_at) VALUES (?, ?, ?, 'upload', ?, ?, ?, ?)",
            (title, mediaType, f"/uploads/{safe_name}", dumps(_tags(tags)), dumps({"filename": file.filename, "contentType": file.content_type}), now, now),
        )
        row = conn.execute("SELECT * FROM media WHERE id=?", (cur.lastrowid,)).fetchone()
    return {"item": media_dict(row)}


@app.delete("/api/media/{media_id}")
def delete_media(media_id: int) -> dict[str, Any]:
    with db() as conn:
        row = conn.execute("SELECT * FROM media WHERE id=?", (media_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Media not found")
        conn.execute("DELETE FROM media WHERE id=?", (media_id,))
    return {"ok": True}


@app.get("/uploads/{file_name:path}")
def uploaded_file(file_name: str) -> FileResponse:
    path = (UPLOAD_DIR / file_name).resolve()
    if not str(path).startswith(str(UPLOAD_DIR.resolve())) or not path.exists():
        raise HTTPException(404, "File not found")
    return FileResponse(path)


@app.get("/api/devices")
def list_devices() -> dict[str, Any]:
    with db() as conn:
        rows = conn.execute("SELECT * FROM devices ORDER BY updated_at DESC, id DESC").fetchall()
    return {"items": [device_dict(r) for r in rows]}


@app.post("/api/devices")
def create_device(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    now = utcnow()
    device_type = str(payload.get("deviceType") or payload.get("device_type") or "mock").lower()
    label = str(payload.get("label") or device_type.title()).strip()
    with db() as conn:
        cur = conn.execute(
            "INSERT INTO devices(user_id, device_type, label, config_json, status, created_at, updated_at) VALUES (1, ?, ?, ?, 'unknown', ?, ?)",
            (device_type, label, dumps(payload.get("config", {})), now, now),
        )
        row = conn.execute("SELECT * FROM devices WHERE id=?", (cur.lastrowid,)).fetchone()
    return {"item": device_dict(row)}


@app.put("/api/devices/{device_id}")
def update_device(device_id: int, payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    with db() as conn:
        row = conn.execute("SELECT * FROM devices WHERE id=?", (device_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Device not found")
        conn.execute("UPDATE devices SET label=?, config_json=?, updated_at=? WHERE id=?", (payload.get("label", row["label"]), dumps(payload.get("config", loads(row["config_json"], {}))), utcnow(), device_id))
        new_row = conn.execute("SELECT * FROM devices WHERE id=?", (device_id,)).fetchone()
    return {"item": device_dict(new_row)}


@app.delete("/api/devices/{device_id}")
def delete_device(device_id: int) -> dict[str, Any]:
    with db() as conn:
        row = conn.execute("SELECT * FROM devices WHERE id=?", (device_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Device not found")
        conn.execute("DELETE FROM devices WHERE id=?", (device_id,))
    return {"ok": True}


@app.post("/api/devices/{device_id}/test")
def device_test(device_id: int) -> dict[str, Any]:
    with db() as conn:
        row = conn.execute("SELECT * FROM devices WHERE id=?", (device_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Device not found")
        response = test_device(row["device_type"], loads(row["config_json"], {}))
        status_text = "connected" if response.get("ok") else "error"
        conn.execute("UPDATE devices SET status=?, last_seen_at=?, updated_at=? WHERE id=?", (status_text, utcnow() if response.get("ok") else row["last_seen_at"], utcnow(), device_id))
        conn.execute("INSERT INTO device_command_logs(device_id, user_id, command_json, response_json, status, created_at) VALUES (?, 1, ?, ?, ?, ?)", (device_id, dumps({"action": "test"}), dumps(response), status_text, utcnow()))
    return {"status": status_text, "response": response}


@app.post("/api/devices/{device_id}/command")
def device_command(device_id: int, payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    command = payload.get("command", payload)
    with db() as conn:
        row = conn.execute("SELECT * FROM devices WHERE id=?", (device_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Device not found")
        response = send_device_command(row["device_type"], loads(row["config_json"], {}), command)
        status_text = "sent" if response.get("ok") else "error"
        conn.execute("INSERT INTO device_command_logs(device_id, user_id, command_json, response_json, status, created_at) VALUES (?, 1, ?, ?, ?, ?)", (device_id, dumps(command), dumps(response), status_text, utcnow()))
        if response.get("ok"):
            conn.execute("UPDATE devices SET status='connected', last_seen_at=?, updated_at=? WHERE id=?", (utcnow(), utcnow(), device_id))
    return {"status": status_text, "response": response}


@app.post("/api/devices/{device_id}/upload-script/{script_id}")
def upload_script_to_device(device_id: int, script_id: int) -> dict[str, Any]:
    script = script_dict(get_script_row(script_id))
    with db() as conn:
        row = conn.execute("SELECT * FROM devices WHERE id=?", (device_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Device not found")
        if row["device_type"] != "handy":
            raise HTTPException(400, "Script upload is implemented for The Handy devices")
        funscript = events_to_funscript(script["events"])
        response = upload_handy_script(loads(row["config_json"], {}), funscript)
        conn.execute("INSERT INTO device_command_logs(device_id, user_id, command_json, response_json, status, created_at) VALUES (?, 1, ?, ?, ?, ?)", (device_id, dumps({"action": "upload-script", "scriptId": script_id}), dumps(response), "sent" if response.get("ok") else "error", utcnow()))
    return {"response": response, "funscriptSummary": {"actions": len(funscript.get("actions", []))}}


@app.get("/api/legal/{document}")
def legal(document: str) -> dict[str, Any]:
    docs = {
        "terms": "Self-hosted personal-use software. You are responsible for lawful content, consent, safety, and third-party device credentials.",
        "privacy": "This app stores scripts, games, media metadata, uploads, and device settings in your local SQLite database/volume.",
    }
    if document not in docs:
        raise HTTPException(404, "Document not found")
    return {"document": document, "title": document.title(), "body": docs[document]}


@app.get("/robots.txt", response_class=PlainTextResponse)
def robots() -> str:
    return "User-agent: *\nDisallow: /\n"


@app.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
def unknown_api(path: str) -> JSONResponse:
    return JSONResponse({"detail": "API endpoint not found"}, status_code=404)


@app.get("/{path:path}")
def spa(path: str = "") -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")
