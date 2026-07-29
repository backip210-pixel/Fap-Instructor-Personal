from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="fi-core-test-")
os.environ["SEED_DEMO_DATA"] = "true"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


def assert_ok(response, expected_status=200):
    assert response.status_code == expected_status, f"{response.request.method} {response.request.url} -> {response.status_code}: {response.text}"
    return response


def main() -> None:
    with TestClient(app) as client:
        health = assert_ok(client.get("/api/health")).json()
        assert health["mode"] == "simple-media-metronome"

        config = assert_ok(client.get("/api/config")).json()
        assert "eventCatalog" in config
        assert "payments" not in config

        # Removed features should be absent.
        assert client.get("/api/auth/me").status_code == 404
        assert client.get("/api/subscription").status_code == 404
        assert client.get("/api/devices").status_code == 404

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
                    "title": "Smoke media script",
                    "description": "Created by smoke test",
                    "tags": ["smoke", "media"],
                    "events": [
                        {"type": "chat-message", "text": "Test", "duration": 1},
                        {"type": "metronome", "tempo": 80},
                        {"type": "media", "url": "https://example.com/image.jpg", "mediaType": "image", "duration": 2},
                        {"type": "stroke", "tempo": 80, "duration": 2, "grip": "normal", "style": "full"},
                        {"type": "game-over", "message": "done"},
                    ],
                },
            )
        ).json()["item"]
        assert created["durationSeconds"] >= 5

        updated = assert_ok(
            client.put(
                f"/api/scripts/{created['id']}",
                json={**created, "title": "Smoke script updated"},
            )
        ).json()["item"]
        assert updated["title"] == "Smoke script updated"

        media = assert_ok(client.post("/api/media", json={"title": "Example image", "mediaType": "image", "url": "https://example.com/image.jpg"})).json()["item"]
        assert media["mediaType"] == "image"
        media_items = assert_ok(client.get("/api/media")).json()["items"]
        assert media_items

        generators = assert_ok(client.get("/api/game-generators")).json()["items"]
        assert generators, "seeded generator should exist"
        game = assert_ok(client.post(f"/api/game-generators/{generators[0]['id']}/start", json={})).json()["item"]
        assert game["events"]
        assert_ok(client.get(f"/api/games/{game['id']}"))

        assert_ok(client.get("/"))
        assert_ok(client.get("/static/logo.svg"))

    print("Smoke test passed")


if __name__ == "__main__":
    main()
