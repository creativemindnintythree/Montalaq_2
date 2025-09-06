# Healthchecks — Agency 013.7

This document records how liveness/readiness are implemented and used in Montalaq_2.

## Endpoints

### `/healthz` — liveness
- Returns `{"status":"ok"}` with HTTP **200**.
- **Does not** touch DB or Redis.
- Purpose: lets Docker know the web process is up and responding.

### `/readyz` — readiness
- Returns a JSON object like `{"db":"ok","redis":"ok"}` with HTTP **200** when all dependencies are fine.
- If DB or Redis check fails, returns HTTP **503** with details (e.g. `{"db":"error:...","redis":"ok"}`).
- Purpose: used by humans/ops (not Docker) to confirm dependencies are ready.

## Why both?
- **Liveness** is a lightweight “is the server alive?” probe.
- **Readiness** is a deeper “can the service do useful work?” probe (DB + cache/Redis).

## Docker healthcheck (web)
The web container uses `/healthz` as its healthcheck.

```yaml
# docker-compose.override.yml
services:
  web:
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/healthz"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 20s

  worker:
    depends_on:
      web:
        condition: service_healthy
      redis:
        condition: service_started

  beat:
    depends_on:
      web:
        condition: service_healthy
      redis:
        condition: service_started