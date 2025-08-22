#!/bin/bash
# scripts/soak_5x2.sh
# 30-minute soak test for 5 pairs × 2 timeframes.
# Runs Redis, Celery worker & beat, Django dev server.
# Watch /api/ingestion/status every minute; expect GREEN most cycles.

set -euo pipefail

# Start Redis in background
echo "🔵 Starting Redis server..."
redis-server --daemonize yes

# Start Celery worker (4 concurrency, default queue)
echo "🔵 Starting Celery worker..."
celery -A montalaq_project worker -l info -Q celery -c 4 &

# Start Celery beat scheduler
echo "🔵 Starting Celery beat..."
celery -A montalaq_project beat -l info &

# Start Django dev server
echo "🔵 Starting Django runserver..."
python manage.py runserver 0.0.0.0:8000 &

echo "✅ All services started. Beginning 30-minute soak..."
echo "ℹ️ Every minute, we’ll check /api/ingestion/status for freshness."

# Loop for ~30 minutes (30 iterations of 60s)
for i in $(seq 1 30); do
  sleep 60
  echo "---- Minute $i ----"
  curl -s http://127.0.0.1:8000/api/ingestion/status | jq '.'
done

echo "🎯 Soak test complete. Check logs and DB for anomalies."
