# README_notifications.md

> Montalaq_2 • Notifications (Admin + Signing + Guards + Ops)

This doc is the operator/dev guide for the 013.3 Notifications tasking that Ninja 913.4 hardened in Steps **d/e/f** and documented in **g**.

## Contents
- [Overview](#overview)
- [Models & Admin](#models--admin)
- [Runtime Settings](#runtime-settings)
- [Webhook Signing](#webhook-signing)
- [Guards & Behavior](#guards--behavior)
- [Local Smoke Tests](#local-smoke-tests)
- [Unit Tests](#unit-tests)
- [Troubleshooting](#troubleshooting)
- [Rollback & Safety](#rollback--safety)

---

## Overview
- Multi-channel delivery: **email**, **webhook**, **slack** (via webhook)
- Optional **HMAC signing** for generic webhooks
- Guardrails: **per-minute rate limit**, **dedupe**, **per-event severity floors**, **dry-run**
- Admin UI for `NotificationChannel` (enable/disable, floors, events JSON, config JSON)

**Entrypoint:** `backend/tasks/notify.py` → `send_notification(event, severity, payload)`

---

## Models & Admin
**Model:** `backend.models.NotificationChannel`
- `name` (unique), `channel_type` in {`EMAIL`,`WEBHOOK`,`SLACK`}
- `enabled` (bool)
- `min_severity` in {`DEBUG`,`INFO`,`WARNING`,`ERROR`,`CRITICAL`}
- `events` (JSON): e.g. `{ "signal": true, "failure": true, "freshness": true }`
- `config` (JSON): channel-specific (e.g. webhook `url`, email `from_addr`)
- `dedupe_window_sec` (default 900)
- `created_at`, `updated_at`

**Admin:** `backend/admin.py`
- List: `name, channel_type, enabled, min_severity, created_at, updated_at`
- Filters: `channel_type, enabled, min_severity`
- Editable JSON: `events`, `config` (light validation in `clean()`)

**Access:** `http://localhost:8000/admin/`

---

## Runtime Settings
`montalaq_project/settings.py → NOTIFICATION_DEFAULTS`
```python
{
  "dry_run": env_bool("NOTIFY_DRY_RUN", False),
  "max_events_per_minute": env_int("NOTIFY_MAX_PER_MIN", 60),
  "dedupe_window_sec": env_int("NOTIFY_DEDUPE_SEC", 900),
  "channels": {
    "webhook": {
      "enabled": env_bool("NOTIFY_WEBHOOK_ENABLED", True),
      "url": os.getenv("NOTIFY_WEBHOOK_URL", "https://httpbin.org/post"),
      "secret": os.getenv("NOTIFY_WEBHOOK_SECRET", "")  # empty disables signing
    },
    "email": {
      "enabled": env_bool("NOTIFY_EMAIL_ENABLED", False),
      "from_addr": os.getenv("NOTIFY_EMAIL_FROM", "noreply@example.com"),
      "to_addrs": env_list("NOTIFY_EMAIL_TO"),
    },
    "slack": {
      "enabled": env_bool("NOTIFY_SLACK_ENABLED", False),
      "webhook_url": os.getenv("NOTIFY_SLACK_WEBHOOK", ""),
    },
  },
}
```
**Note:** Listening is determined by **DB channels** (Admin) via `events[event] == true`.

---

## Webhook Signing
When `NOTIFY_WEBHOOK_SECRET` (or `channels.webhook.secret`) is **non-empty**:
- Compute body: compact, sorted JSON (`separators=(",", ":")`, `sort_keys=True`).
- Compute timestamp `ts` (UTC, second precision) and signature:
  - `X-Timestamp: <ts>`
  - `X-Signature: sha256=<hex(hmac_sha256(secret, f"{ts}\n{body}"))>`
- Request: `POST url` with `Content-Type: application/json` and the above headers.

**Disable:** set secret to empty `""`.

---

## Guards & Behavior
- **Dry-run** (`dry_run: true`): skip actual sends; log `notify.skip: dry-run ...`.
- **Per-event floor**: if no enabled channel **listening** to `event`, log `no-channel-listening` and return. Else enforce min severity across candidates.
- **Per-minute limit**: coarse throttle per `(event, severity)` with `max_events_per_minute`.
- **Dedupe**: for `event == "signal"` with bar context, suppress duplicates within `dedupe_window_sec` (default 900s).
- **Retries**: webhook sender logs error and re-raises; Celery task is decorated with autoretry/backoff.

---

## Local Smoke Tests
> Run from repo root. These commands assume Docker Compose services are up.

### 1) Health + Celery
```bash
curl -sfS localhost:8000/healthz && echo OK
docker compose exec worker celery -A montalaq_project inspect ping
```

### 2) Inspect runtime defaults
```bash
docker compose exec worker bash -lc 'python - << "PY"
import json, os
from django.conf import settings
print("ENV NOTIFY_DRY_RUN=", os.getenv("NOTIFY_DRY_RUN"))
print("ENV NOTIFY_WEBHOOK_SECRET=", os.getenv("NOTIFY_WEBHOOK_SECRET"))
print(json.dumps(settings.NOTIFICATION_DEFAULTS, indent=2))
PY'
```

### 3) (Optional) Enable dry-run + secret in overrides
```yaml
# docker-compose.override.yml
services:
  worker:
    environment:
      NOTIFY_DRY_RUN: "1"
      NOTIFY_WEBHOOK_SECRET: "dev-secret-123"
```
Apply:
```bash
docker compose up -d --force-recreate --no-deps worker
```

### 4) Trigger a notification
```bash
TS=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
ARGS='["signal","INFO",{"symbol":"EURUSD","timeframe":"15m","bar_ts":"'"$TS"'","title":"cli-smoke"}]'
docker compose exec worker celery -A montalaq_project call backend.tasks.notify.send_notification --args="$ARGS"
```

### 5) Inspect logs
```bash
docker compose logs --since=5m worker | egrep -i "notify\\.(skip|sent|error|rate-limited|deduped|no-channel-listening)"
```

Expected patterns:
- Dry-run on: `notify.skip: dry-run ...`
- Dedupe on same bar: `notify.skip: deduped key=...`
- No listener: `notify.skip: no-channel-listening event=...`
- On error: `notify.error: ...` followed by Celery autoretry.

---

## Unit Tests
Location: `backend/tests/test_notify_guards.py`
- Creates a DB-backed `WEBHOOK` channel listening to `signal`.
- Tests:
  - **dry-run** short-circuits network
  - **webhook 500** triggers **autoretry** (exception raised)
  - **rate-limit** enforces ≤1 call/min when limit = 1
  - **dedupe** suppresses same `(symbol, timeframe, bar_ts)`

Run:
```bash
docker compose exec -e DJANGO_SETTINGS_MODULE=montalaq_project.settings web python -m pytest -q backend/tests/test_notify_guards.py
```

---

## Troubleshooting
- **No logs:** widen window `--since=10m`; ensure worker is running.
- **Always `no-channel-listening`:** create/enable a channel in Admin with `events[event] = true` and floor ≤ severity.
- **No signing headers:** ensure `NOTIFY_WEBHOOK_SECRET` is non-empty and reflected in `NOTIFICATION_DEFAULTS["channels"]["webhook"]["secret"]`.
- **Dedupe surprises:** use fresh `bar_ts` each try.
- **Retry loops:** verify receiver health; Celery max retries = 5 by default.

---

## Rollback & Safety
- Flip `NOTIFY_DRY_RUN=1` to halt sends.
- Disable channels in Admin (`enabled = False`).
- Remove `NOTIFY_WEBHOOK_SECRET` (or set empty) to disable signing.
- Everything is feature-flagged via env and Admin; no code rollback needed.

---

# scripts/notify_smoke.sh
```bash
#!/usr/bin/env bash
set -euo pipefail

# Simple smoke driver for notifications pipeline.
# Usage: ./scripts/notify_smoke.sh [symbol] [tf] [title]
# Defaults: EURUSD 15m cli-smoke

SYMBOL=${1:-EURUSD}
TF=${2:-15m}
TITLE=${3:-cli-smoke}

TS=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
ARGS='["signal","INFO",{"symbol":"'"$SYMBOL"'","timeframe":"'"$TF"'","bar_ts":"'"$TS"'","title":"'"$TITLE"'"}]'

echo "[notify-smoke] sending: $SYMBOL $TF @ $TS — $TITLE"
docker compose exec worker celery -A montalaq_project call backend.tasks.notify.send_notification --args="$ARGS"

echo "[notify-smoke] recent worker logs:" >&2
docker compose logs --since=5m worker | egrep -i "notify\\.(skip|sent|error|rate-limited|deduped|no-channel-listening)" || true
```

**Install & run:**
```bash
mkdir -p scripts
printf "%s" "$(sed -n 's/^```bash$//;s/^```$//;/^#\!\/usr\/bin\/env bash/,/```/p' README_notifications.md)" > scripts/notify_smoke.sh
chmod +x scripts/notify_smoke.sh
./scripts/notify_smoke.sh
```

---

## Merge notes
- Branch: `agency-013.6g-docs`
- Files:
  - `README_notifications.md`
  - `scripts/notify_smoke.sh`
- Commit:
```bash
git checkout -b agency-013.6g-docs
# (save the files above)
git add README_notifications.md scripts/notify_smoke.sh
git commit -m "913.4: docs + ops smoke for notifications (admin, signing, guards)"
git push -u origin agency-013.6g-docs
```

