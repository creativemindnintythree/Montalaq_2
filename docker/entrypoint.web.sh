#!/usr/bin/env bash
set -euo pipefail

# Wait for Redis to be ready
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

# Run migrations (idempotent)
python manage.py migrate --noinput

# Start the web server (use gunicorn; switch to runserver for hot reload)
if [ "${DEBUG:-1}" = "1" ]; then
  # Dev: live reload server (optional)
  exec python manage.py runserver 0.0.0.0:${PORT:-8000}
else
  # Prod-ish: gunicorn
  exec gunicorn montalaq_project.wsgi:application \
      --bind 0.0.0.0:${PORT:-8000} \
      --workers 3 \
      --timeout 60
fi
