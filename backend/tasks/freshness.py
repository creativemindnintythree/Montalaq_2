from django.db.utils import OperationalError
import random, time
# backend/tasks/freshness.py

import os
from datetime import datetime, timedelta
from typing import Optional, Tuple, Dict, Any

import yaml
from django.apps import apps
from django.db import transaction
from django.utils import timezone


# =========================
# Config helpers
# =========================

_DEFAULT_CFG: Dict[str, Any] = {
    # Seconds per timeframe (scheduler/freshness cadence).
    # We deliberately add tolerance (e.g., 1m → 90s) to avoid flapping.
    "freshness_seconds": {
        "1m": 90,     # 1.5× grace
        "5m": 360,    # 6 minutes
        "15m": 1080,  # 18 minutes
        "1h": 5400,   # 90 minutes
    }
}


def _cfg() -> Dict[str, Any]:
    """
    Load orchestration config (e.g., freshness cadence per timeframe).
    Expected file: backend/orchestration/watchlist.yaml
    Falls back to _DEFAULT_CFG if file/keys are missing.
    """
    path = "backend/orchestration/watchlist.yaml"
    data: Dict[str, Any] = {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except FileNotFoundError:
        data = {}

    # Merge (shallow) with defaults
    out = dict(_DEFAULT_CFG)
    out.setdefault("freshness_seconds", {})
    out["freshness_seconds"] = {
        **_DEFAULT_CFG.get("freshness_seconds", {}),
        **(data.get("freshness_seconds") or {}),
    }
    return out


# =========================
# DB helpers
# =========================

def _last_ingested_bar(symbol: str, timeframe: str):
    """
    Return the most recently *inserted* MarketData row (by PK), not max(timestamp).
    This matches ingestion semantics where late/out-of-order inserts can happen.
    """
    MarketData = apps.get_model("backend", "MarketData")
    return (
        MarketData.objects.filter(symbol=symbol, timeframe=timeframe)
        .order_by("-id")
        .first()
    )


# =========================
# Provider key-age helpers
# =========================

def _parse_issued_at(env_var: str) -> Optional[datetime]:
    """
    Parse ISO8601-like issued-at env variables; return None if not set or invalid.
    Accepts 'YYYY-MM-DD' or full ISO strings; makes them timezone-aware.
    """
    val = os.getenv(env_var, "").strip()
    if not val:
        return None

    dt: Optional[datetime] = None
    try:
        # Handle trailing Z by converting to +00:00; fall back to date-only.
        try:
            dt = datetime.fromisoformat(val.replace("Z", "+00:00"))
        except Exception:
            dt = datetime.strptime(val, "%Y-%m-%d")
    except Exception:
        return None

    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = timezone.make_aware(dt, timezone=timezone.get_current_timezone())
    return dt


def _provider_key_age_days(provider: str) -> Optional[int]:
    """
    Compute key age in days based on provider-specific issued-at env.
      - AllTick:     ALLTICK_KEY_ISSUED_AT
      - TwelveData:  TWELVEDATA_KEY_ISSUED_AT
    Returns None if unknown/not set.
    """
    if provider == "TwelveData":
        issued_at = _parse_issued_at("TWELVEDATA_KEY_ISSUED_AT")
    else:  # default to AllTick per policy
        issued_at = _parse_issued_at("ALLTICK_KEY_ISSUED_AT")

    if not issued_at:
        return None
    return (timezone.now().date() - issued_at.date()).days


# =========================
# Public freshness utilities
# =========================

def is_fresh(symbol: str, timeframe: str) -> Tuple[bool, Optional[datetime], str]:
    """
    Freshness gate:
      GREEN: age <= 1× cadence
      AMBER: 1.5× < age < 3× cadence
      RED:   otherwise (includes 1× < age <= 1.5×, and age >= 3×)

    Returns: (is_green: bool, last_bar_ts: datetime|None, color: str)
    """
    cfg = _cfg()
    th = cfg["freshness_seconds"][timeframe]  # raises KeyError if unknown timeframe
    last = _last_ingested_bar(symbol, timeframe)
    if not last:
        return (False, None, "RED")

    last_ts = getattr(last, "timestamp", None)
    if not last_ts:
        return (False, None, "RED")

    age = (timezone.now() - last_ts).total_seconds()

    if age <= th:
        return (True, last_ts, "GREEN")
    if 1.5 * th < age < 3 * th:
        return (False, last_ts, "AMBER")
    return (False, last_ts, "RED")


def _compute_kpis_5m(symbol: str, timeframe: str) -> tuple[int, int, Optional[int]]:
    """
    Compute simple rolling KPIs over the last 5 minutes from AnalysisLog:
      - ok (state COMPLETE)
      - fail (state FAILED)
      - median latency (ms), using latency_ms if present else (finished_at - started_at)

    Uses started_at for the window (aligned with earlier scheduler semantics).

    Returns (ok_5m, fail_5m, median_latency_ms|None)
    """
    AnalysisLog = apps.get_model("backend", "AnalysisLog")
    since = timezone.now() - timedelta(minutes=5)

    qs = AnalysisLog.objects.filter(
        symbol=symbol,
        timeframe=timeframe,
        started_at__gte=since,
    )

    ok = qs.filter(state="COMPLETE").count()
    fail = qs.filter(state="FAILED").count()

    latencies: list[int] = []
    for rec in qs.values("latency_ms", "started_at", "finished_at"):
        ms = rec.get("latency_ms")
        if ms is None:
            s, e = rec.get("started_at"), rec.get("finished_at")
            if s and e:
                ms = int((e - s).total_seconds() * 1000)
        if ms is not None and ms >= 0:
            latencies.append(ms)

    if not latencies:
        median_ms = None
    else:
        latencies.sort()
        mid = len(latencies) // 2
        median_ms = latencies[mid] if len(latencies) % 2 else int((latencies[mid - 1] + latencies[mid]) / 2)

    return ok, fail, median_ms


# =========================
# Status upsert (heartbeat + freshness)
# =========================

def update_ingestion_status(
    symbol: str,
    timeframe: str,
    *,
    provider: Optional[str] = None,
    fallback_active: bool = False,
    override_freshness_state: Optional[str] = None,
    override_data_freshness_sec: Optional[int] = None,
    last_bar_ts: Optional[datetime] = None,
    last_ingest_ts: Optional[datetime] = None,
):
    """
    Upsert and RETURN the IngestionStatus row for (symbol, timeframe).

    013.4 requirements:
      • Always write last_seen_at = now (heartbeat) every cycle, even if bars don’t advance.
      • Populate freshness fields: freshness_state ∈ {GREEN, AMBER, RED} and data_freshness_sec.

    Also maintains:
      • provider (default AllTick if unknown)
      • last_bar_ts, last_ingest_ts
      • fallback_active
      • key_age_days (derived from provider env)
      • rolling 5-minute KPIs: analyses_ok_5m, analyses_fail_5m, median_latency_ms
    """
    IngestionStatus = apps.get_model("backend", "IngestionStatus")

    cfg = _cfg()
    th = cfg["freshness_seconds"][timeframe]  # KeyError for truly unknown tfs

    # Detect latest bar (by insertion order) to compute default refs
    last_bar = _last_ingested_bar(symbol, timeframe)
    detected_last_bar_ts = getattr(last_bar, "timestamp", None)
    # Some pipelines may annotate an ingestion time; if not, use bar ts as proxy
    detected_ingest_ts = getattr(last_bar, "ingested_at", None) or detected_last_bar_ts

    # Decide provider
    if provider:
        effective_provider = provider
    else:
        effective_provider = getattr(last_bar, "provider", None) or "AllTick"

    # Freshness computation (unless fully overridden)
    if override_freshness_state is not None and override_data_freshness_sec is not None:
        freshness = override_freshness_state
        age_sec = override_data_freshness_sec
    else:
        ref_ts = last_bar_ts or detected_last_bar_ts
        if ref_ts:
            age_sec = int((timezone.now() - ref_ts).total_seconds())
            if age_sec <= th:
                freshness = "GREEN"
            elif 1.5 * th < age_sec < 3 * th:
                freshness = "AMBER"
            else:
                freshness = "RED"
        else:
            freshness = "RED"
            age_sec = None

    # KPIs over 5 minutes
    ok_5m, fail_5m, median_latency_ms = _compute_kpis_5m(symbol, timeframe)

    # Heartbeat is always 'now' — even if bar didn’t move (quiet market)
    heartbeat_now = timezone.now()

    # Upsert status with a single atomic section
    with transaction.atomic():
        obj, _created = IngestionStatus.objects.select_for_update().get_or_create(
            symbol=symbol,
            timeframe=timeframe,
            defaults=dict(
                freshness_state=freshness,
                data_freshness_sec=age_sec,
                last_bar_ts=last_bar_ts or detected_last_bar_ts,
                last_ingest_ts=last_ingest_ts or detected_ingest_ts,
                provider=effective_provider,
                fallback_active=fallback_active,
                key_age_days=_provider_key_age_days(effective_provider),
                analyses_ok_5m=ok_5m,
                analyses_fail_5m=fail_5m,
                median_latency_ms=median_latency_ms,
                last_seen_at=heartbeat_now,
            ),
        )

        # Update mutable fields every cycle
        fields_to_update = [
            "freshness_state",
            "data_freshness_sec",
            "last_seen_at",            # heartbeat (ALWAYS)
            "analyses_ok_5m",
            "analyses_fail_5m",
            "median_latency_ms",
            "fallback_active",
        ]

        obj.freshness_state = freshness
        obj.data_freshness_sec = age_sec
        obj.last_seen_at = heartbeat_now
        obj.analyses_ok_5m = ok_5m
        obj.analyses_fail_5m = fail_5m
        obj.median_latency_ms = median_latency_ms
        obj.fallback_active = bool(fallback_active)

        # These we update when we have new information (don’t thrash needlessly):
        if (last_bar_ts or detected_last_bar_ts) and obj.last_bar_ts != (last_bar_ts or detected_last_bar_ts):
            obj.last_bar_ts = last_bar_ts or detected_last_bar_ts
            fields_to_update.append("last_bar_ts")

        if (last_ingest_ts or detected_ingest_ts) and obj.last_ingest_ts != (last_ingest_ts or detected_ingest_ts):
            obj.last_ingest_ts = last_ingest_ts or detected_ingest_ts
            fields_to_update.append("last_ingest_ts")

        if obj.provider != effective_provider:
            obj.provider = effective_provider
            fields_to_update.append("provider")

        # Provider key age is cheap to recompute
        key_age = _provider_key_age_days(effective_provider)
        if obj.key_age_days != key_age:
            obj.key_age_days = key_age
            fields_to_update.append("key_age_days")

        if fields_to_update:
            _save_with_retry(obj, update_fields=fields_to_update)

    return obj
def _save_with_retry(obj, update_fields=None, attempts=6, base=0.05):
    """
    Exponential backoff with jitter for sqlite OperationalError: database is locked
    attempts: 6 → ~0.05, 0.1, 0.2, 0.4, 0.8, 1.6s (+ jitter)
    """
    for i in range(attempts):
        try:
            obj.save(update_fields=update_fields)
            return
        except OperationalError as e:
            msg = str(e).lower()
            if "database is locked" not in msg and "database is busy" not in msg:
                raise
            sleep_s = base * (2 ** i) + random.uniform(0, base)
            time.sleep(sleep_s)
    obj.save(update_fields=update_fields)
