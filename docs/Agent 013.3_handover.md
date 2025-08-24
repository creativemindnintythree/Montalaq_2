docs/Agent 013.3_handover.md
Title

Agent 013.3 — Public Analysis API, Notifications, Escalation & Breaker (compatible with 013.2.1)

Scope (Recap)

Introduce public Analysis API (/api/analysis/latest, /api/analysis/history) with caching.

Notifications plumbing (email/webhook/Slack), dedupe per bar, rate‑limit per minute.

Escalation ladder (INFO → WARN → ERROR → CRITICAL) driven by freshness + recent failures.

Per‑pair circuit breaker (never global) that skips only affected symbols/timeframes.

Alignment with 013.2.1 patch: centralized error taxonomy, KPI rollup cadence in settings, provider abstraction.

1) Central Error Taxonomy

Source: backend/errors.py

from enum import Enum
from typing import Type, Dict

class ErrorCode(str, Enum):
    INGESTION_TIMEOUT = "INGESTION_TIMEOUT"
    PROVIDER_DISCONNECTED = "PROVIDER_DISCONNECTED"
    DUPLICATE_TICK = "DUPLICATE_TICK"
    FRESHNESS_THRESHOLD_EXCEEDED = "FRESHNESS_THRESHOLD_EXCEEDED"
    ANALYSIS_ERR = "ANALYSIS_ERR"   # used when ML/analysis throws RuntimeError
    UNKNOWN = "UNKNOWN"

EXCEPTION_MAP: Dict[Type[BaseException], ErrorCode] = {
    TimeoutError: ErrorCode.INGESTION_TIMEOUT,
    ConnectionError: ErrorCode.PROVIDER_DISCONNECTED,
    RuntimeError: ErrorCode.ANALYSIS_ERR,
}


Usage:

TradeAnalysis.finish_run_fail(exc) persists status="FAILED", error_code, error_message.

Analysis task maps exceptions via EXCEPTION_MAP before closing AnalysisLog.

2) Public Analysis API
Files

backend/api/analysis/serializers.py — latest/history serializers (+ optional top_features)

backend/api/analysis/views.py — validates pair & tf, caches with ANALYSIS_API_CACHE_TTL (default 30s)

backend/api/analysis/urls.py — routes

montalaq_project/urls.py — includes /api/analysis/…

backend/api/schema.py — OpenAPI JSON & docs

Endpoints

GET /api/analysis/latest?pair=EURUSD&tf=1m

GET /api/analysis/history?pair=EURUSD&tf=1m&limit=100

Response fields (latest/history items):
symbol, timeframe, bar_ts, status, final_decision, rule_confidence_score, ml_confidence, composite_score, stop_loss, take_profit, error_code, error_message, top_features?

Caching:

Configure via ANALYSIS_API_CACHE_TTL (seconds). If unset, defaults to 30.

3) Ingestion Status API (013.3 Additions)

File: backend/api/status/serializers.py & backend/api/status/views.py

Adds fields per pair record:

provider (from DB, choices: AllTick, TwelveData)

escalation_level (INFO|WARN|ERROR|CRITICAL)

breaker_open (true|false)

Optional top‑level providers_summary included by the view.

4) Notifications

File: backend/tasks/notify.py

Retries with backoff for channel sends.

Dedupe (cache) & per‑minute rate‑limit.

Dry‑run toggle for safe validation.

Payloads may include error_code: ErrorCode.*.

Signal hook: backend/tasks/analysis_hooks.py

On COMPLETE + composite_score >= threshold, dedupe per (symbol, timeframe, bar_ts).

Writes IngestionStatus.last_signal_bar_ts for DB-level dedupe.

Config (settings.py → NOTIFICATION_DEFAULTS):

NOTIFICATION_DEFAULTS = {
  "composite_notify_threshold": int(os.getenv("ANALYSIS_NOTIFY_THRESHOLD","70")),
  "dedupe_window_sec": int(os.getenv("ANALYSIS_NOTIFY_DEDUPE_SEC","900")),
  "channels": {
     "email":   {"enabled": env("NOTIFY_EMAIL_ENABLED")==1, "from_addr": ..., "to_addrs": [...]},
     "webhook": {"enabled": env("NOTIFY_WEBHOOK_ENABLED")==1, "url": ...},
     "slack":   {"enabled": env("NOTIFY_SLACK_ENABLED")==1, "webhook_url": ...},
  },
  "dry_run": env("NOTIFY_DRY_RUN")==1,
  "max_events_per_minute": int(os.getenv("NOTIFY_RATE_LIMIT_PER_MIN","60")),
}

Channel Matrix
Channel	Status	Notes
Email	✅	SMTP or local relay; uses from_addr, to_addrs
Webhook	✅	Generic JSON POST to url
Slack	✅	Incoming‑webhook compatible (webhook_url)
Discord	Later	Placeholder; add a channel adapter when needed
5) Escalation Ladder & Circuit Breaker

File: backend/tasks/escalation.py

Evaluates per (symbol,timeframe) using freshness + recent fails.

Stores escalation_level and breaker_open on IngestionStatus.

Notifies on level changes (includes last failed error_code when present).

Ladder Rules

WARN: AMBER ≥ 2 cycles OR fails_5m ≥ 2

ERROR: current freshness RED OR fails_5m ≥ 3

CRITICAL: RED sustained (≥ 3 cycles) OR breaker already open

Breaker Policy (per pair, never global)

Opens when persistent ERROR across checks or RED ≥ 2 cycles.

Remains open until separate closure logic (future task) or operator action.

Scheduler attachment:

@app.on_after_configure inside escalation.py registers periodic eval (beat).

6) Scheduler (Per‑Pair Breaker Isolation)

File: backend/tasks/scheduler.py

Reads backend/orchestration/watchlist.yaml.

Skips only pairs where breaker_open=True for that (symbol,timeframe).

Otherwise: if freshness GREEN → enqueue analysis; else → update status.

st = IngestionStatus.objects.filter(symbol=sym, timeframe=tf).first()
if st and st.breaker_open:
    continue  # skip only this pair

7) Ops & Environment Toggles

settings.py (cadence & intervals)

KPI_ROLLUP_INTERVAL_SEC = int(os.getenv("KPI_ROLLUP_INTERVAL_SEC", "60"))
ESCALATION_EVAL_INTERVAL_SEC = int(os.getenv("ESCALATION_EVAL_INTERVAL_SEC","60"))
CIRCUIT_BREAKER_INTERVAL_SEC = int(os.getenv("CIRCUIT_BREAKER_INTERVAL_SEC","60"))
ANALYSIS_API_CACHE_TTL = int(os.getenv("ANALYSIS_API_CACHE_TTL","30"))


Celery Beat (settings‑driven): montalaq_project/celery.py

Keeps 0131-tick-every-60s.

Adds:

escalation-eval → backend.tasks.escalation.evaluate_escalations @ ESCALATION_EVAL_INTERVAL_SEC.

circuit-breaker → backend.tasks.escalation.circuit_breaker_tick (stub hook) @ CIRCUIT_BREAKER_INTERVAL_SEC.

KPI rollup is registered in celery_tasks/rollup_kpis.py via @app.on_after_configure (no hard‑code).

Windows note: use Celery --pool=solo to avoid billiard handle errors.

8) Data Model Touchpoints

backend/models.py

IngestionStatus has provider choices: AllTick, TwelveData (default AllTick).

Adds/uses: escalation_level, breaker_open, last_signal_bar_ts, last_notify_at.

TradeAnalysis.finish_run_fail(exc) uses error taxonomy.

9) Seed & Sanity

Seed channels (if not present):

python manage.py shell
>>> from scripts import seed_notification_channels
>>> seed_notification_channels.run()
# ✅ Created channel: email / webhook / slack


Static/collect:

python manage.py collectstatic --noinput


Run stack (Windows‑friendly):

redis-server
celery -A montalaq_project worker -l info --pool=solo -Q celery
celery -A montalaq_project beat -l info
python manage.py runserver

10) cURL / PowerShell Examples
Analysis (latest)
# bash/curl
curl -s "http://127.0.0.1:8000/api/analysis/latest?pair=EURUSD&tf=1m" | jq

# PowerShell
irm "http://127.0.0.1:8000/api/analysis/latest?pair=EURUSD&tf=1m" | ConvertTo-Json -Depth 6

Analysis (history, limit)
curl -s "http://127.0.0.1:8000/api/analysis/history?pair=EURUSD&tf=1m&limit=100" | jq

irm "http://127.0.0.1:8000/api/analysis/history?pair=EURUSD&tf=1m&limit=100" | ConvertTo-Json -Depth 6

Ingestion Status
curl -s "http://127.0.0.1:8000/api/ingestion/status" | jq

irm "http://127.0.0.1:8000/api/ingestion/status" | ConvertTo-Json -Depth 6

OpenAPI Schema / Docs
curl -s "http://127.0.0.1:8000/api/schema" | jq
# docs:
# http://127.0.0.1:8000/api/docs

11) Tests (added/updated for 013.3)

tests/test_agent0133_api.py — 400 on missing params; latest/history payloads.

tests/test_agent0133_notifications.py — dedupe per bar; threshold gating.

tests/test_agent0133_notify_ratelimit.py — per‑minute channel rate limit.

tests/test_agent0133_escalation.py — level transitions & breaker open/persist.

tests/test_agent0133_breaker_isolation.py — scheduler skips only broken pairs.

Existing 013.2 tests remain green with the 013.2.1 taxonomy (e.g., ANALYSIS_ERR).

Run:

pytest -q -k "0133 or 0132" --ds=montalaq_project.settings

12) Known Deferables / Next

Discord channel adapter (webhook variant).

Breaker close policy: implement circuit_breaker_tick to auto‑close on sustained GREEN + zero fails for N cycles, or leave as ops/manual.

Extend schema examples with end‑to‑end samples when Agency 011 exposes top_features consistently.

13) Acceptance Checklist

 /api/analysis/latest & /history return correct shapes; cached.

 /api/ingestion/status includes provider, escalation_level, breaker_open.

 Notifications dedupe per bar; threshold respected; rate‑limit enforced.

 Escalation ladder transitions as specified; breaker is per pair only.

 Central ErrorCode taxonomy in use across analysis failure paths.

 Beat schedules driven from settings; no legacy KPI hard‑coded entries.

HoA Verdict (009.5): Ready for integration with 016 (Notification delivery UX) and 017/019 (surface states in UI).