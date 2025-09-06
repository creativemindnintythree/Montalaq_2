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