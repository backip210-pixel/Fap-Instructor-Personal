<p align="center">
  <img src="app/static/logo-wordmark.svg" alt="Fap Instructor Personal" width="760" />
</p>

# Fap Instructor Personal

A very small personal Docker app for the core functionality only:

- Add/upload images and videos
- Add remote image/video/audio/embed URLs
- Build simple timed scripts
- Play scripts with countdowns and a metronome
- Use a standalone metronome
- Generate simple timed metronome sessions

Removed on purpose:

- Login/auth/admin
- Age gate
- Payments/subscriptions/Patreon
- Toy/device integrations
- WebSocket/challenger features
- External service dependencies

## Docker image

```text
ghcr.io/backip210-pixel/fap-instructor-personal:latest
```

## ZimaOS compose

If ZimaOS gives `invalid mount config for type "bind": field Source must not be empty`, use this **no-volume** compose first and delete any Storage/Mount rows in the ZimaOS UI.

```yaml
services:
  fapinstructor:
    image: ghcr.io/backip210-pixel/fap-instructor-personal:latest
    container_name: fap-instructor-personal
    ports:
      - "8090:8080"
    environment:
      APP_NAME: "Fap Instructor Personal"
      PUBLIC_BASE_URL: "http://YOUR-ZIMAOS-IP:8090"
      DATA_DIR: "/tmp/fapinstructor-data"
      SEED_DEMO_DATA: "true"
    restart: unless-stopped
```

Open:

```text
http://YOUR-ZIMAOS-IP:8090
```

No login is required. This no-volume version may not persist data after container recreation, but it avoids ZimaOS mount errors. Add persistence later only after the app starts.

## Run locally

```bash
cp .env.example .env
docker compose up --build
```

Open:

```text
http://localhost:8080
```

## Data

Data lives in the `/data` volume:

```text
/data/app.db
/data/uploads/
```

## Tests

```bash
pip install -r requirements-dev.txt
python -m py_compile app/*.py
node --check app/static/app.js
python tests/smoke_test.py
```

## API

- `GET /api/health`
- `GET/POST /api/scripts`
- `GET/PUT/DELETE /api/scripts/{id}`
- `GET /api/scripts/{id}/export/funscript`
- `GET /api/media`
- `POST /api/media`
- `POST /api/media/upload`
- `GET /api/game-generators`
- `POST /api/game-generators/{id}/start`
- `GET /api/games`
- `GET /api/games/{id}`
