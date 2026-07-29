# ZimaOS deployment

This is now the stripped-down build: no login, no admin, no age gate, no payments, no subscriptions. It should start as a normal container and immediately serve the app.

Image:

```text
ghcr.io/backip210-pixel/fap-instructor-personal:latest
```

## Make GHCR image pullable

If the ZimaOS install cannot pull the image, make the package public:

1. GitHub repo: `backip210-pixel/Fap-Instructor-Personal`
2. **Packages**
3. `fap-instructor-personal`
4. **Package settings**
5. Set visibility to **Public**

Or SSH into ZimaOS and log in:

```bash
docker login ghcr.io -u backip210-pixel
```

## ZimaOS custom compose

Paste this into ZimaOS custom Docker Compose:

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
      HANDY_API_BASE: "https://www.handyfeeling.com/api/handy/v2"
      HANDY_SCRIPT_API: "https://scripts01.handyfeeling.com/api/script/v0"
      LOVENSE_API_TOKEN: ""
      LOVENSE_BASIC_API: "https://api.lovense-api.com/api/basicApi"
      AUTOBLOW_LATENCY_URL: "https://latency.autoblowapi.com/autoblow/connected"
      LANGUAGETOOL_API: ""
    volumes:
      - /DATA/AppData/fapinstructor-personal:/data
    restart: unless-stopped
```

Replace:

```text
YOUR-ZIMAOS-IP
```

Then open:

```text
http://YOUR-ZIMAOS-IP:8080
```

## If ZimaOS says "setting up"

Try these checks over SSH:

```bash
docker ps -a | grep fap-instructor
docker logs --tail=200 fap-instructor-personal
docker pull ghcr.io/backip210-pixel/fap-instructor-personal:latest
```

If the image pull fails, the GHCR package is private or ZimaOS is not logged into GHCR.

## If port 8080 is busy

Change:

```yaml
ports:
  - "8080:8080"
```

to:

```yaml
ports:
  - "8090:8080"
```

And update:

```yaml
PUBLIC_BASE_URL: "http://YOUR-ZIMAOS-IP:8090"
```

Open:

```text
http://YOUR-ZIMAOS-IP:8090
```

## Data path

Persistent data is stored here on ZimaOS:

```text
/DATA/AppData/fapinstructor-personal
```

Reset all app data:

```bash
docker stop fap-instructor-personal
docker rm fap-instructor-personal
sudo rm -rf /DATA/AppData/fapinstructor-personal
mkdir -p /DATA/AppData/fapinstructor-personal
```
