#!/usr/bin/env bash
set -euo pipefail

# Wait for Redis
python - <<'PY'
import os, time, sys
import redis
url = os.environ.get("REDIS_URL", "redis://redis:6379/0")
for i in range(60):
    try:
        r = redis.from_url(url)
        r.ping()
        sys.exit(0)
    except Exception:
        time.sleep(1)
print("Redis not ready after 60s", file=sys.stderr)
sys.exit(1)
PY

# Ensure beat directory exists (persistent schedule)
mkdir -p /app/celerybeat

# Start Celery beat
exec celery -A montalaq_project beat -l info --schedule /app/celerybeat/celerybeat-schedule
