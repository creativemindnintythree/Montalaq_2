from django.utils import timezone
from django.apps import apps
import yaml
import statistics


def _cfg():
    with open("backend/orchestration/watchlist.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _last_ingested_bar(symbol: str, timeframe: str):
    """
    Return the most recently *inserted* MarketData row (by PK), not the max timestamp.
    This matches scheduler/ingestion behavior and test expectations where successive
    inserts may have older timestamps.
    """
    MarketData = apps.get_model("backend", "MarketData")
    return (
        MarketData.objects.filter(symbol=symbol, timeframe=timeframe)
        .order_by("-id")
        .first()
    )


def is_fresh(symbol: str, timeframe: str):
    cfg = _cfg()
    th = cfg["freshness_seconds"][timeframe]
    last = _last_ingested_bar(symbol, timeframe)
    if not last:
        return (False, None, "RED")
    age = (timezone.now() - last.timestamp).total_seconds()
    # GREEN: age <= 1× cadence
    if age <= th:
        return (True, last.timestamp, "GREEN")
    # AMBER: 1.5× < age < 3× cadence  (i.e., > 1.5× and < 3×)
    if age > 1.5 * th and age < 3 * th:
        return (False, last.timestamp, "AMBER")
    # RED: age >= 3× cadence (and also when between 1× and 1.5× we treat as RED by spec here)
    return (False, last.timestamp, "RED")


def update_ingestion_status(symbol: str, timeframe: str):
    IngestionStatus = apps.get_model("backend", "IngestionStatus")
    AnalysisLog = apps.get_model("backend", "AnalysisLog")

    cfg = _cfg()
    th = cfg["freshness_seconds"][timeframe]

    last_bar = _last_ingested_bar(symbol, timeframe)
    last_bar_ts = getattr(last_bar, "timestamp", None)

    # Compute freshness
    if last_bar_ts:
        age = (timezone.now() - last_bar_ts).total_seconds()
        if age <= th:
            freshness = "GREEN"
        elif age > 1.5 * th and age < 3 * th:
            freshness = "AMBER"
        else:
            freshness = "RED"
    else:
        age = None
        freshness = "RED"

    # "Last ingest" as "most recent insert time" ≈ updated_at/created_at; fallback to now
    last_ingest_ts = getattr(last_bar, "timestamp", None)  # if you have created_at, prefer it

    # Compute analysis KPIs (last 5m window)
    since = timezone.now() - timezone.timedelta(minutes=5)
    recent_logs = AnalysisLog.objects.filter(
        symbol=symbol, timeframe=timeframe, started_at__gte=since
    )
    ok = recent_logs.filter(state="COMPLETE").count()
    fail = recent_logs.filter(state="FAILED").count()
    latencies = list(
        recent_logs.exclude(latency_ms=None).values_list("latency_ms", flat=True)
    )
    median_latency = int(statistics.median(latencies)) if latencies else None

    # Provider info can be set by ingestion step (and overwritten here if needed)
    provider = getattr(last_bar, "provider", None) if last_bar else None

    obj, _ = IngestionStatus.objects.update_or_create(
        symbol=symbol,
        timeframe=timeframe,
        defaults=dict(
            last_bar_ts=last_bar_ts,
            last_ingest_ts=last_ingest_ts,
            freshness_state=freshness,
            data_freshness_sec=age,
            provider=provider,
            key_age_days=None,       # set by ingestion stewardship (Step 7)
            fallback_active=False,   # set by ingestion stewardship (Step 7)
            analyses_ok_5m=ok,
            analyses_fail_5m=fail,
            median_latency_ms=median_latency,
        ),
    )
    return obj
