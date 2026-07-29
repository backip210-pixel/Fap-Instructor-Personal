from __future__ import annotations

import os
import secrets
import shutil
from pathlib import Path
from typing import Any

from fastapi import Body, FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from .database import UPLOAD_DIR, db, dumps, init_db, loads, utcnow
from .game import EVENT_CATALOG, compute_duration, events_to_funscript, generate_game_from_config, normalize_events

APP_NAME = os.getenv("APP_NAME", "Fap Instructor Personal")
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "http://localhost:8080")
SEED_DEMO_DATA = os.getenv("SEED_DEMO_DATA", "true").lower() == "true"

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(title=APP_NAME, version="3.0.0-simple-core")
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


def _row_dict(row: Any) -> dict[str, Any]:
    return dict(row) if row is not None else {}


def script_dict(row: Any) -> dict[str, Any]:
    d = _row_dict(row)
    d["tags"] = loads(d.pop("tags_json", "[]"), [])
    d["events"] = loads(d.pop("events_json", "[]"), [])
    d["durationSeconds"] = d.pop("duration_seconds", 0)
    d["createdAt"] = d.pop("created_at", None)
    d["updatedAt"] = d.pop("updated_at", None)
    for key in ["created_by", "created_by_username", "instructor_id", "instructor_name", "visibility", "required_subscription"]:
        d.pop(key, None)
    return d


def media_dict(row: Any) -> dict[str, Any]:
    d = _row_dict(row)
    d["tags"] = loads(d.pop("tags_json", "[]"), [])
    d["metadata"] = loads(d.pop("metadata_json", "{}"), {})
    d["mediaType"] = d.pop("media_type", "")
    d["createdAt"] = d.pop("created_at", None)
    d["updatedAt"] = d.pop("updated_at", None)
    d.pop("created_by", None)
    return d


def generator_dict(row: Any) -> dict[str, Any]:
    d = _row_dict(row)
    d["tags"] = loads(d.pop("tags_json", "[]"), [])
    d["config"] = loads(d.pop("config_json", "{}"), {})
    d["createdAt"] = d.pop("created_at", None)
    d["updatedAt"] = d.pop("updated_at", None)
    for key in ["created_by", "visibility", "created_by_username"]:
        d.pop(key, None)
    return d


def game_dict(row: Any) -> dict[str, Any]:
    d = _row_dict(row)
    d["tags"] = loads(d.pop("tags_json", "[]"), [])
    d["events"] = loads(d.pop("events_json", "[]"), [])
    d["settings"] = loads(d.pop("settings_json", "{}"), {})
    d["durationSeconds"] = d.pop("duration_seconds", 0)
    d["createdAt"] = d.pop("created_at", None)
    d["updatedAt"] = d.pop("updated_at", None)
    d.pop("created_by", None)
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
            demo_events = normalize_events([
                {"type": "chat-message", "text": "Welcome. Start the metronome and follow the timer.", "speech": "Welcome. Start the metronome and follow the timer.", "duration": 4},
                {"type": "metronome", "tempo": 60, "measure": "4/4"},
                {"type": "stroke", "tempo": 60, "duration": 20, "grip": "normal", "style": "full"},
                {"type": "wait", "duration": 8},
                {"type": "stroke", "tempo": 90, "duration": 24, "grip": "normal", "style": "short"},
                {"type": "instruction", "title": "Check in", "description": "Pause, slow down, or continue.", "duration": 6, "options": [{"title": "Continue", "events": []}, {"title": "Slow tempo", "events": [{"type": "stroke-tempo", "tempo": 50}]}]},
                {"type": "game-over", "message": "Demo complete"},
            ])
            conn.execute(
                """
                INSERT INTO scripts(title, description, tags_json, events_json, duration_seconds, difficulty, votes, plays, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                ("Demo metronome script", "A short local demo with timed events and metronome changes.", dumps(["demo", "metronome"]), dumps(demo_events), compute_duration(demo_events), "normal", 2, 0, now, now),
            )
            media_events = normalize_events([
                {"type": "chat-message", "text": "This template demonstrates an image or video cue.", "duration": 4},
                {"type": "metronome", "tempo": 72},
                {"type": "media", "url": "", "mediaType": "video", "duration": 12},
                {"type": "stroke", "tempo": 72, "duration": 20, "grip": "normal", "style": "full"},
                {"type": "game-over", "message": "Template complete"},
            ])
            conn.execute(
                """
                INSERT INTO scripts(title, description, tags_json, events_json, duration_seconds, difficulty, votes, plays, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                ("Media cue template", "Add images/videos in Media, then paste the URL into a media event.", dumps(["media", "template"]), dumps(media_events), compute_duration(media_events), "easy", 1, 0, now, now),
            )

        if conn.execute("SELECT COUNT(*) FROM game_generators").fetchone()[0] == 0:
            config = {"durationMinutes": 5, "minTempo": 45, "maxTempo": 110, "intensity": "medium", "includeEdges": False, "includeInstructions": True, "outcome": "deny"}
            conn.execute(
                "INSERT INTO game_generators(name, description, tags_json, config_json, runs, created_at, updated_at) VALUES (?, ?, ?, ?, 0, ?, ?)",
                ("Quick metronome generator", "Generate a timed metronome session.", dumps(["demo", "generator", "metronome"]), dumps(config), now, now),
            )


@app.on_event("startup")
async def on_startup() -> None:
    seed_data()


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"ok": True, "name": APP_NAME, "version": app.version, "time": utcnow(), "mode": "simple-media-metronome"}


@app.get("/api/config")
def config() -> dict[str, Any]:
    return {"appName": APP_NAME, "eventCatalog": EVENT_CATALOG}


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
            "UPDATE scripts SET title=?, description=?, tags_json=?, events_json=?, duration_seconds=?, difficulty=?, updated_at=? WHERE id=?",
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


@app.get("/api/game-generators")
def list_game_generators(limit: int = Query(50, ge=1, le=200)) -> dict[str, Any]:
    with db() as conn:
        rows = conn.execute("SELECT * FROM game_generators ORDER BY updated_at DESC, id DESC LIMIT ?", (limit,)).fetchall()
    return {"items": [generator_dict(r) for r in rows]}


@app.post("/api/game-generators/{generator_id}/start")
def start_game_generator(generator_id: int, payload: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    with db() as conn:
        row = conn.execute("SELECT * FROM game_generators WHERE id=?", (generator_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Generator not found")
    generator = generator_dict(row)
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
        game_row = conn.execute("SELECT * FROM games WHERE id=?", (cur.lastrowid,)).fetchone()
    return {"item": game_dict(game_row)}


@app.get("/api/games")
def list_games(limit: int = Query(50, ge=1, le=200)) -> dict[str, Any]:
    with db() as conn:
        rows = conn.execute("SELECT * FROM games ORDER BY created_at DESC, id DESC LIMIT ?", (limit,)).fetchall()
    return {"items": [game_dict(r) for r in rows]}


@app.get("/api/games/{game_id}")
def get_game(game_id: int) -> dict[str, Any]:
    with db() as conn:
        row = conn.execute("SELECT * FROM games WHERE id=?", (game_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Game not found")
    return {"item": game_dict(row)}


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


@app.get("/api/legal/{document}")
def legal(document: str) -> dict[str, Any]:
    docs = {
        "terms": "Self-hosted personal-use software. You are responsible for lawful content, consent, and safety.",
        "privacy": "This app stores scripts, games, media metadata, and uploads in your local SQLite database/volume.",
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
