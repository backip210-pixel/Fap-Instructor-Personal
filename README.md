<p align="center">
  <img src="app/static/logo-wordmark.svg" alt="Fap Instructor Personal" width="760" />
</p>

# Fap Instructor Personal

A stripped-down personal Docker app for the core functionality only:

- scripts
- script builder
- player
- metronome
- procedural generators
- generated games
- media library
- simple device hooks

No login. No admin. No age gate. No payments. No subscriptions. No Patreon. No WebSocket rooms. Just the local app.

## Docker image

```text
ghcr.io/backip210-pixel/fap-instructor-personal:latest
```

## Run locally

```bash
cp .env.example .env
docker compose up --build
```

Open:

```text
http://localhost:8080
```

## ZimaOS compose

Use this in a ZimaOS custom Docker Compose app. Change `YOUR-ZIMAOS-IP` if you want the base URL to match your server.

```yaml
services:
  fapinstructor:
    image: ghcr.io/backip210-pixel/fap-instructor-personal:latest
    container_name: fap-instructor-personal
    ports:
      - "8080:8080"
    environment:
      APP_NAME: "Fap Instructor Personal"
      PUBLIC_BASE_URL: "http://YOUR-ZIMAOS-IP:8080"
      DATA_DIR: "/data"
      SEED_DEMO_DATA: "true"
      ENABLE_REMOTE_INTEGRATIONS: "false"
    volumes:
      - /DATA/AppData/fapinstructor-personal:/data
    restart: unless-stopped
```

Then open:

```text
http://YOUR-ZIMAOS-IP:8080
```

## If 8080 is busy

Use another host port, for example:

```yaml
ports:
  - "8090:8080"
environment:
  PUBLIC_BASE_URL: "http://YOUR-ZIMAOS-IP:8090"
```

Then open:

```text
http://YOUR-ZIMAOS-IP:8090
```

## Data

Data is stored in the mounted volume/path:

```text
/data/app.db
/data/uploads/
```

For ZimaOS, the recommended host path is:

```text
/DATA/AppData/fapinstructor-personal
```

## Updating on ZimaOS/SSH

```bash
docker pull ghcr.io/backip210-pixel/fap-instructor-personal:latest
docker compose up -d
```

## Development tests

```bash
pip install -r requirements-dev.txt
python -m py_compile app/*.py
node --check app/static/app.js
python tests/smoke_test.py
```

## Included API

- `GET /api/health`
- `GET/POST /api/scripts`
- `GET/PUT/DELETE /api/scripts/{id}`
- `GET /api/scripts/{id}/export/funscript`
- `GET/POST /api/game-generators`
- `POST /api/game-generators/{id}/start`
- `GET /api/games`
- `GET /api/games/{id}`
- `GET/POST /api/media`
- `POST /api/media/upload`
- `GET/POST /api/devices`
- `POST /api/devices/{id}/test`
- `POST /api/devices/{id}/command`
