# ZimaOS deployment

If ZimaOS shows this error:

```text
invalid mount config for type "bind": field Source must not be empty
```

it means ZimaOS is creating a storage/bind-mount row with a blank host/source path. The fix is to deploy **without any volumes/mounts** first.

This build is intentionally simple:

- no login
- no admin
- no age gate
- no payments/subscriptions
- no toy/device integrations
- no external services

## Image

```text
ghcr.io/backip210-pixel/fap-instructor-personal:latest
```

## Use this exact ZimaOS compose first

Important: this compose has **no `volumes:` section**.

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

Replace:

```text
YOUR-ZIMAOS-IP
```

Open:

```text
http://YOUR-ZIMAOS-IP:8090
```

## Critical ZimaOS UI step

In the ZimaOS app/custom-compose screen, look for sections called any of these:

- Storage
- Volumes
- Mounts
- Path mappings
- Directories

Delete every row there for now.

Do **not** leave a blank storage row. A blank row causes:

```text
field Source must not be empty
```

## Why DATA_DIR uses /tmp here

The compose above uses:

```yaml
DATA_DIR: "/tmp/fapinstructor-data"
```

That avoids needing `/data` or any mounted path while we confirm the app starts.

This means data may not persist if the container is recreated. Once the app is confirmed running, we can add persistence back with a valid ZimaOS path.

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

Also remove old containers before trying again:

```bash
docker stop fap-instructor-personal || true
docker rm fap-instructor-personal || true
```

## Add persistence later only after it runs

Once the no-volume version works, we can add persistence with a real host path. For example:

```bash
mkdir -p /DATA/AppData/fapinstructor-personal
chmod 777 /DATA/AppData/fapinstructor-personal
```

Then use:

```yaml
volumes:
  - /DATA/AppData/fapinstructor-personal:/data
```

and change:

```yaml
DATA_DIR: "/data"
```

But do not add this until the no-volume version works.
