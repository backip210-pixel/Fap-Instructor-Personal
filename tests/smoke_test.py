from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Configure before importing the app.
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="fi-personal-test-")
os.environ["SEED_DEMO_DATA"] = "true"
os.environ["SEED_ADMIN_EMAIL"] = "admin@example.com"
os.environ["SEED_ADMIN_PASSWORD"] = "admin123!"
os.environ["ALLOW_REGISTRATION"] = "true"
os.environ["ENABLE_REMOTE_INTEGRATIONS"] = "false"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


def assert_ok(response, expected_status=200):
    assert response.status_code == expected_status, f"{response.request.method} {response.request.url} -> {response.status_code}: {response.text}"
    return response


def main() -> None:
    with TestClient(app) as client:
        assert_ok(client.get("/api/health"))
        config = assert_ok(client.get("/api/config")).json()
        assert "eventCatalog" in config
        assert "payments" not in config

        me = client.get("/api/auth/me")
        assert me.status_code == 401

        login = assert_ok(
            client.post(
                "/api/auth/login",
                json={"email": "admin@example.com", "password": "admin123!"},
            )
        ).json()
        assert login["user"]["role"] == "admin"
        assert "subscriptionStatus" not in login["user"]

        scripts = assert_ok(client.get("/api/scripts?limit=5")).json()["items"]
        assert scripts, "seeded scripts should exist"
        first_script = scripts[0]
        assert "requiredSubscription" not in first_script
        assert_ok(client.get(f"/api/scripts/{first_script['id']}"))
        assert_ok(client.get(f"/api/scripts/{first_script['id']}/export/funscript"))

        created = assert_ok(
            client.post(
                "/api/scripts",
                json={
                    "title": "Smoke script",
                    "description": "Created by smoke test",
                    "visibility": "private",
                    "tags": ["smoke"],
                    "events": [
                        {"type": "chat-message", "text": "Test", "duration": 1},
                        {"type": "metronome", "tempo": 80},
                        {"type": "stroke", "tempo": 80, "duration": 2, "grip": "normal", "style": "full"},
                        {"type": "game-over", "message": "done"},
                    ],
                },
            )
        ).json()["item"]
        assert created["durationSeconds"] >= 3

        generators = assert_ok(client.get("/api/game-generators")).json()["items"]
        assert generators, "seeded generator should exist"
        game = assert_ok(client.post(f"/api/game-generators/{generators[0]['id']}/start", json={})).json()["item"]
        assert game["events"]
        assert_ok(client.get(f"/api/games/{game['id']}"))

        device = assert_ok(
            client.post("/api/devices", json={"deviceType": "mock", "label": "Smoke mock", "config": {}})
        ).json()["item"]
        assert_ok(client.post(f"/api/devices/{device['id']}/test", json={})).json()
        cmd = assert_ok(client.post(f"/api/devices/{device['id']}/command", json={"command": {"action": "tempo", "tempo": 88}})).json()
        assert cmd["status"] == "sent"

        room = assert_ok(client.post("/api/challenger/rooms", json={"title": "Smoke room"})).json()["item"]
        assert room["code"]
        assert_ok(client.get(f"/api/challenger/rooms/{room['code']}"))

        admin = assert_ok(client.get("/api/admin/stats")).json()
        assert "payments" not in admin["counts"]

        assert_ok(client.get("/"))
        assert client.get("/api/subscription").status_code == 404

    print("Smoke test passed")


if __name__ == "__main__":
    main()
