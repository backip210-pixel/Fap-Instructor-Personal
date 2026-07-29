# ZimaOS deployment

This is the stripped-down core build:

- no login
- no admin
- no age gate
- no payments/subscriptions
- no toy/device integrations
- no external services

It only serves scripts, media upload/URL storage, a script player, and a metronome.

## Image

```text
ghcr.io/backip210-pixel/fap-instructor-personal:latest
```

## Recommended ZimaOS compose

This uses host port `8090` to avoid `8080` conflicts and a Docker named volume to avoid host directory permission issues.

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
      DATA_DIR: "/data"
      SEED_DEMO_DATA: "true"
    volumes:
      - fapinstructor-data:/data
    restart: unless-stopped

volumes:
  fapinstructor-data:
```

Replace:

```text
YOUR-ZIMAOS-IP
```

Open:

```text
http://YOUR-ZIMAOS-IP:8090
```

## If the image will not pull

Make the GHCR package public:

1. GitHub repo: `backip210-pixel/Fap-Instructor-Personal`
2. **Packages**
3. `fap-instructor-personal`
4. **Package settings**
5. Visibility: **Public**

Or SSH into ZimaOS and run:

```bash
docker login ghcr.io -u backip210-pixel
docker pull ghcr.io/backip210-pixel/fap-instructor-personal:latest
```

## If ZimaOS still says "setting up"

SSH into the ZimaOS box:

```bash
docker ps -a | grep fap-instructor
docker logs --tail=200 fap-instructor-personal
```

Common fixes:

- Use host port `8090` instead of `8080`
- Use the named volume compose above instead of a host path
- Make the GHCR image public or log into GHCR

## Reset data

```bash
docker stop fap-instructor-personal
docker rm fap-instructor-personal
docker volume rm fapinstructor-data
```

Then redeploy.
