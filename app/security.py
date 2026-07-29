from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import Cookie, Depends, HTTPException, Response, WebSocket, status

from .database import db, row_to_dict, utcnow

SESSION_COOKIE = "fi_session"
SESSION_DAYS = int(os.getenv("SESSION_DAYS", "30"))
SECURE_COOKIES = os.getenv("SECURE_COOKIES", "false").lower() == "true"


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    rounds = 310_000
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, rounds)
    return f"pbkdf2_sha256${rounds}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, rounds_s, salt_s, digest_s = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        rounds = int(rounds_s)
        salt = base64.urlsafe_b64decode(salt_s + "=" * (-len(salt_s) % 4))
        expected = base64.urlsafe_b64decode(digest_s + "=" * (-len(digest_s) % 4))
        got = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, rounds)
        return hmac.compare_digest(got, expected)
    except Exception:
        return False


def create_session(response: Response, user_id: int) -> str:
    token = secrets.token_urlsafe(48)
    now = datetime.now(timezone.utc)
    expires = now + timedelta(days=SESSION_DAYS)
    with db() as conn:
        conn.execute(
            "INSERT INTO sessions(token, user_id, expires_at, created_at) VALUES (?, ?, ?, ?)",
            (token, user_id, expires.isoformat(), now.isoformat()),
        )
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=SESSION_DAYS * 24 * 60 * 60,
        httponly=True,
        secure=SECURE_COOKIES,
        samesite="lax",
        path="/",
    )
    return token


def clear_session(response: Response, token: str | None = None) -> None:
    if token:
        with db() as conn:
            conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
    response.delete_cookie(SESSION_COOKIE, path="/")


def _get_user_for_token(token: str | None) -> dict[str, Any] | None:
    if not token:
        return None
    with db() as conn:
        row = conn.execute(
            """
            SELECT users.* FROM sessions
            JOIN users ON users.id = sessions.user_id
            WHERE sessions.token = ? AND sessions.expires_at > ?
            """,
            (token, utcnow()),
        ).fetchone()
        user = row_to_dict(row, {"settings_json"})
        if user:
            user["settings"] = user.pop("settings_json", {})
        return user


def optional_user(fi_session: str | None = Cookie(default=None)) -> dict[str, Any] | None:
    return _get_user_for_token(fi_session)


def require_user(user: dict[str, Any] | None = Depends(optional_user)) -> dict[str, Any]:
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    return user


def require_admin(user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    if user.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user


async def websocket_user(websocket: WebSocket) -> dict[str, Any] | None:
    token = websocket.cookies.get(SESSION_COOKIE)
    return _get_user_for_token(token)
