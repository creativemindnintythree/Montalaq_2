# backend/tasks/kpis.py
from typing import Optional
import statistics
from django.utils import timezone
from django.apps import apps
from celery import shared_task


def _pairs_from_logs(since, symbol: Optional[str] = None, timeframe: Optional[str] = None):
    AnalysisLog = apps.get_model("backend", "AnalysisLog")
    qs = AnalysisLog.objects.filter(started_at__gte=since)
    if symbol:
        qs = qs.filter(symbol=symbol)
    if timeframe:
        qs = qs.filter(timeframe=timeframe)
    return qs.values("symbol", "timeframe").distinct()


def _compute_metrics(symbol: str, timeframe: str, since):
    """
    KPI definition for 013.2 tests:
      - analyses_ok_5m: COUNT of COMPLETE runs in the window (includes NO_TRADE completes).
      - analyses_fail_5m: COUNT of FAILED runs in the window.
      - median_latency_ms: median latency across COMPLETE + FAILED in the window.
    """
    AnalysisLog = apps.get_model("backend", "AnalysisLog")
    qs = AnalysisLog.objects.filter(
        symbol=symbol, timeframe=timeframe, started_at__gte=since
    )
    ok = qs.filter(state="COMPLETE").count()
    fail = qs.filter(state="FAILED").count()
    latencies = list(qs.exclude(latency_ms=None).values_list("latency_ms", flat=True))
    median_latency = int(statistics.median(latencies)) if latencies else None
    return ok, fail, median_latency


def _upsert_status(symbol: str, timeframe: str, ok: int, fail: int, median_latency):
    IngestionStatus = apps.get_model("backend", "IngestionStatus")
    obj, _ = IngestionStatus.objects.get_or_create(symbol=symbol, timeframe=timeframe)
    obj.analyses_ok_5m = ok
    obj.analyses_fail_5m = fail
    obj.median_latency_ms = median_latency
    obj.save(
        update_fields=[
            "analyses_ok_5m",
            "analyses_fail_5m",
            "median_latency_ms",
            "updated_at",
        ]
    )
    return obj


@shared_task
def rollup_5m(symbol: Optional[str] = None, timeframe: Optional[str] = None):
    """
    Recompute last-5-minute KPIs per (symbol,timeframe) from AnalysisLog and
    write into IngestionStatus. Accepts optional symbol/timeframe to scope the rollup.
    """
    since = timezone.now() - timezone.timedelta(minutes=5)

    pairs = list(_pairs_from_logs(since, symbol=symbol, timeframe=timeframe))
    if not pairs:
        return {"updated": 0}

    updated = 0
    for p in pairs:
        sym = p["symbol"]
        tf = p["timeframe"]
        ok, fail, median_latency = _compute_metrics(sym, tf, since)
        _upsert_status(sym, tf, ok, fail, median_latency)
        updated += 1

    return {"updated": updated, "window_start": since.isoformat()}
