# celery_tasks/rollup_kpis.py
"""
Periodic KPI rollup for ingestion/analysis health (Agent 013.2.1 compatible)

- Schedules itself using settings.KPI_ROLLUP_INTERVAL_SEC (no hard-coded seconds).
- Computes last-5-min window KPIs from AnalysisLog:
    * analyses_ok_5m
    * analyses_fail_5m
    * median_latency_ms
- Writes KPIs into IngestionStatus per (symbol, timeframe) row.
- Safe to run frequently; idempotent updates.

Requires models created by 013.2:
  - backend.models.AnalysisLog (state: PENDING|COMPLETE|FAILED, latency_ms, finished_at, symbol, timeframe)
  - backend.models.IngestionStatus (analyses_ok_5m, analyses_fail_5m, median_latency_ms, symbol, timeframe)
"""

from __future__ import annotations

import statistics
from datetime import timedelta

from django.apps import apps
from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from montalaq_project.celery import app


@app.task(name="kpi.rollup_ingestion_kpis")
def rollup_ingestion_kpis() -> dict:
    """
    Roll up KPIs for the last 5 minutes per (symbol, timeframe).
    Returns a summary dict for observability.
    """
    AnalysisLog = apps.get_model("backend", "AnalysisLog")
    IngestionStatus = apps.get_model("backend", "IngestionStatus")

    now = timezone.now()
    window_start = now - timedelta(minutes=5)

    # Gather all distinct (symbol, timeframe) observed in either AnalysisLog (last day) or IngestionStatus
    recent_pairs = (
        AnalysisLog.objects.filter(finished_at__gte=now - timedelta(days=1))
        .values_list("symbol", "timeframe")
        .distinct()
    )
    status_pairs = (
        IngestionStatus.objects.all()
        .values_list("symbol", "timeframe")
        .distinct()
    )
    pairs = set(recent_pairs) | set(status_pairs)

    summary = {}
    for sym, tf in pairs:
        # Filter logs in the last 5 minutes for this pair/tf
        qs = AnalysisLog.objects.filter(
            symbol=sym,
            timeframe=tf,
            finished_at__gte=window_start,
        )

        ok_count = qs.filter(state="COMPLETE").count()
        fail_count = qs.filter(state="FAILED").count()
        latencies = list(
            qs.filter(~Q(latency_ms=None)).values_list("latency_ms", flat=True)
        )
        median_ms = int(statistics.median(latencies)) if latencies else None

        # Upsert IngestionStatus KPIs for this pair/tf
        # (Do not touch other fields like freshness/provider here.)
        obj, _ = IngestionStatus.objects.get_or_create(symbol=sym, timeframe=tf)
        obj.analyses_ok_5m = ok_count
        obj.analyses_fail_5m = fail_count
