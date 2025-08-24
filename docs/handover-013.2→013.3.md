Handover to Agent 013.3 (/docs/handover-013.2→013.3.md)


📝 Handover from Agent 013.2 → Agent 013.3



From: Agent 009.5 (HOA – Pipeline Orchestration)

To: Agent 013.3 (Execution Agent)

CC: Agent 009 (CSO), Agent 009.1 (Deputy CSO)

Subject: Full Mandate Handover – Agent 013.3 Scope



1\. 📊 State of the Pipeline (post-013.2)



Agent 013.1 gave us the core pipeline spine: ingestion → preprocessing → ML → composite chaining, multi-pair, freshness-driven.

Agent 013.2 hardened it with reliability and monitoring:



Freshness-gated scheduler: Celery beat driver only advances when ticks arrive in acceptable freshness window.



State machine (PENDING → COMPLETE | FAILED): Every ingestion + analysis job now transitions deterministically.



Lifecycle transparency: TradeAnalysis carries status, error\_code, started\_at, finished\_at.



Observability models:



AnalysisLog: JSON details of every run, traceable to pair + TF.



IngestionStatus: freshness/lag tracking, success/failure counts.



API exposure: /api/ingestion/status returns real-time KPIs (uptime, latency, median processing time, fail rates).



Structured logging: logging.yaml writes JSON logs to file/stdout → parseable by ELK or any SIEM.



Soak tested: Stable under multi-hour ingestion runs across pairs.



Regression coverage: 22/22 tests passed, tagged as v0.13.2.



👉 Result: Stable, observable, monitored orchestration spine.



2\. 🎯 013.3 Objectives (Your Mandate)



Your scope is externalization + escalation.

Where 013.2 stopped at internal monitoring, you must connect signals to users and systems.



2.1 Notifications Layer



Add Celery task hooks to push state changes:



Failures (ingestion or analysis) → log + alert.



Success/freshness restoration → info notice.



Deliver multi-channel outputs (configurable):



Email (Django mail backend).



Webhook POSTs (JSON to configured endpoint).



Slack/Discord (via webhook URL).



Add config model: NotificationChannel tied to events.



2.2 Analysis API (public-facing)



New endpoint(s) under /api/analysis/:



/api/analysis/latest?pair=EURUSD\&tf=15m → return most recent TradeAnalysis.



/api/analysis/history?pair=…\&limit=… → batched view.



Response must carry composite score, ML explainability slice, status, timestamps.



Pagination \& caching needed (use Django DRF’s paginator).



2.3 Escalation Logic



Define severity ladder:



INFO → WARN → ERROR → CRITICAL.



Wire into notification layer.



Failures crossing thresholds (e.g., 3 consecutive failures for a pair) → escalate from WARN to CRITICAL.



CRITICAL = system-wide alert (all channels).



2.4 Resilience Enhancements



Add retry policies for Celery tasks (exponential backoff).



Implement circuit breaker: if provider returns bad data for >N minutes, pause tasks \& mark stale.



Extend /api/ingestion/status with escalation\_level.



3\. 🗂 File \& Code Targets



You will work in these specific files (building on 013.2):



Backend models:



backend/models.py → add NotificationChannel, escalation fields in IngestionStatus.



Tasks:



celery\_tasks/notify.py (new) → send alerts.



Extend celery\_tasks/orchestrator.py to trigger notify.



API:



backend/api\_views.py → add /analysis endpoints.



backend/serializers.py → new serializers for TradeAnalysis \& logs.



Settings:



Add NOTIFICATION\_DEFAULTS in settings.py.



Tests:



tests/test\_agent0133\_notifications.py.



tests/test\_agent0133\_api.py.



Regression soak extension under tests/test\_agent0133\_soak.py.



4\. ✅ Success Criteria (Exit Conditions)



For your scope to be archived as done:



Notifications fire on success/fail, routed to at least one channel.



Analysis API returns valid JSON responses, passing schema tests.



Escalation ladder demonstrably escalates (INFO → CRITICAL) with simulated failures.



Retry/circuit breaker logic working in soak tests.



Tests: minimum +10 new cases, all regression passing.



Docs: \_docs\_handover-013.3.md summarizing delivery for 013.4.



5\. 📌 Known Non-Scope (Defer to 013.4+)



Performance optimizations (e.g., async streaming APIs).



Advanced visualization dashboards.



Multi-tenant alert policies.



Historical backfill of notifications.

These will be formalized later.



6\. 🚦 Execution Guidance



Start with notification plumbing (Celery → logging → notify).



Layer in API endpoints second — they depend only on DB, not on live orchestration.



Finish with escalation/circuit breaker, since these ride on top of notifications.



Test early with forced failures (e.g., kill ingestion process) to trigger alerts.



Keep commits atomic: one feature per commit with \[013.3] prefix.



7\. 🔑 Closing Line



Agent 013.2 has handed you a rock-solid monitored core.

Your mandate is to make it outward-facing and operationally safe — connecting pipeline health to humans and systems, and enforcing structured escalation.



Once you’ve done that, Agency 013 will be fully equipped to not just run but to warn, inform, and protect downstream consumers.



Respectfully,

Agent 009.5

Head of Agency 013 (Pipeline Orchestration)

executive summery

Scope delivered in 013.2

State tracking

TradeAnalysis: status, error\_code, error\_message, started\_at, finished\_at.

New AnalysisLog (per-run PENDING→COMPLETE|FAILED with latency \& error fields).

Ingestion KPIs \& freshness

New IngestionStatus (symbol, timeframe, last bar ts, freshness, 5‑min KPIs).

Freshness thresholds: GREEN ≤ 1× cadence, AMBER > 1.5×, RED ≥ 3×.

backend/tasks/freshness.update\_ingestion\_status() implemented.

backend/tasks/kpis.rollup\_5m(symbol?, timeframe?) computes:

analyses\_ok\_5m, analyses\_fail\_5m, median\_latency\_ms.

Gating \& scheduling

scheduler.tick: only schedules analyze\_latest when GREEN.

Beat entries added in montalaq\_project/celery.py for KPI rollup.

API

GET /api/ingestion/status (DRF view + serializer + urls) returns provider, key age, and per-pair freshness + KPIs.

Logging

backend/logging.yaml adds structured JSON sink and Celery error capture.

Tests

tests/test\_0132\_\*:

Failure-state coverage (no-trade, ML exceptions).

KPI rollup correctness \& freshness coloring.

Status API schema.

