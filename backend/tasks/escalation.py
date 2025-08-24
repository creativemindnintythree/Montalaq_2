# backend/tasks/escalation.py
"""
013.3 Escalation ladder + per‑pair circuit breaker

Severity rules (evaluated per (symbol, timeframe)):
• WARN:     AMBER ≥ 2 cycles  OR  fails_5m ≥ 2
• ERROR:    RED               OR  fails_5m ≥ 3
• CRITICAL: RED sustained (≥ 3 cycles)  OR  breaker open

Details
- We track consecutive AMBER/RED/GREEN cycles in Django cache (no schema change).
- We update IngestionStatus.escalation_level and .breaker_open.
- We send a notification on level changes (include last failed AnalysisLog.error_code if any).
- Scheduled by Celery Beat using settings.ESCALATION_EVAL_INTERVAL_SEC and
  settings.CIRCUIT_BREAKER_INTERVAL_SEC (configured in montalaq_project/celery.py).
"""

from __future__ import annotations

from typing import Dict, Optional, Tuple

from celery import shared_task
from django.apps import apps
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from backend.tasks.notify import send_notification
from backend.errors import ErrorCode  # imported for type hints / payloads

# ---------------------------------------------------------------------
# Constants / helpers
# ---------------------------------------------------------------------

LEVELS = ("INFO", "WARN", "ERROR", "CRITICAL")
FRESH_GREEN = "GREEN"
FRESH_AMBER = "AMBER"
FRESH_RED = "RED"

# Cache TTL ~10x evaluation period; minimum 10 minutes
CACHE_TTL = max(int(getattr(settings, "ESCALATION_EVAL_INTERVAL_SEC", 60)) * 10, 600)


def _ck(sym: str, tf: str, kind: str) -> str:
    """Cache key helper."""
    return f"esc:{kind}:{sym}:{tf}"


def _get_last_failed_error_code(symbol: str, timeframe: str) -> Optional[str]:
    """Fetch most recent failed AnalysisLog.error_code (if any)."""
    AnalysisLog = apps.get_model("backend", "AnalysisLog")
    row = (
        AnalysisLog.objects.filter(symbol=symbol, timeframe=timeframe, state="FAILED")
        .only("error_code", "finished_at")
        .order_by("-finished_at")
        .first()
    )
    return getattr(row, "error_code", None) if row else None


def _compute_level(
    freshness: str,
    fails_5m: int,
    amber_cycles: int,
    red_cycles: int,
    breaker_open: bool,
) -> str:
    """Apply the ladder to decide target level."""
    # CRITICAL first if breaker open or RED sustained
    if breaker_open or red_cycles >= 3:
        return "CRITICAL"

    # ERROR if RED now or many recent fails
    if freshness == FRESH_RED or fails_5m >= 3:
        return "ERROR"

    # WARN if prolonged AMBER or some recent fails
    if (freshness == FRESH_AMBER and amber_cycles >= 2) or fails_5m >= 2:
        return "WARN"

    return "INFO"


def _update_counters(symbol: str, timeframe: str, freshness: str) -> Tuple[int, int, int]:
    """
    Update and return (green_cycles, amber_cycles, red_cycles) for this pair/tf.
    Opposing counters reset on transitions.
    """
    g_key = _ck(symbol, timeframe, "green")
    a_key = _ck(symbol, timeframe, "amber")
    r_key = _ck(symbol, timeframe, "red")

    if freshness == FRESH_GREEN:
        g = int(cache.get(g_key, 0)) + 1
        cache.set(g_key, g, CACHE_TTL)
        cache.set(a_key, 0, CACHE_TTL)
        cache.set(r_key, 0, CACHE_TTL)
        return g, 0, 0

    if freshness == FRESH_AMBER:
        a = int(cache.get(a_key, 0)) + 1
        cache.set(a_key, a, CACHE_TTL)
        cache.set(g_key, 0, CACHE_TTL)
        cache.set(r_key, 0, CACHE_TTL)
        return 0, a, 0

    # RED
    r = int(cache.get(r_key, 0)) + 1
    cache.set(r_key, r, CACHE_TTL)
    cache.set(g_key, 0, CACHE_TTL)
    cache.set(a_key, 0, CACHE_TTL)
    return 0, 0, r


def _maybe_open_breaker(
    current_level: str,
    red_cycles: int,
    prev_level: str,
    prev_breaker: bool,
) -> bool:
    """
    Heuristic breaker policy:
      - If already open → stay open.
      - Open if RED for ≥ 2 cycles.
      - Open if ERROR persists (previous ERROR and remains ERROR/CRITICAL).
    """
    if prev_breaker:
        return True
    if red_cycles >= 2:
        return True
    if prev_level == "ERROR" and current_level in ("ERROR", "CRITICAL"):
        return True
    return False


def _maybe_close_breaker(
    breaker_open: bool,
    green_cycles: int,
    fails_5m: int,
) -> bool:
    """
    Close breaker when conditions improve:
      - require >= 2 consecutive GREEN cycles AND fails_5m == 0
    """
    if not breaker_open:
        return False  # nothing to close
    if green_cycles >= 2 and fails_5m == 0:
        return True
    return False


# ---------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------

@shared_task(name="backend.tasks.escalation.evaluate_escalation")
def evaluate_escalation() -> int:
    """
    Iterate all IngestionStatus rows, compute target severity & breaker state,
    update DB on change, and send notifications on transitions.

    Returns: number of rows updated.
    """
    IngestionStatus = apps.get_model("backend", "IngestionStatus")
    updated = 0
    now = timezone.now()

    rows = IngestionStatus.objects.all().only(
        "symbol",
        "timeframe",
        "freshness_state",
        "analyses_ok_5m",
        "analyses_fail_5m",
        "median_latency_ms",
        "escalation_level",
        "breaker_open",
        "provider",
        "fallback_active",
        "key_age_days",
    )

    for r in rows:
        sym = r.symbol
        tf = r.timeframe
        freshness = r.freshness_state or FRESH_RED
        fails_5m = int(r.analyses_fail_5m or 0)

        # Update counters from current freshness
        g_cycles, a_cycles, r_cycles = _update_counters(sym, tf, freshness)

        # Decide level
        next_level = _compute_level(
            freshness=freshness,
            fails_5m=fails_5m,
            amber_cycles=a_cycles,
            red_cycles=r_cycles,
            breaker_open=bool(r.breaker_open),
        )

        # Decide if breaker should be opened (or kept)
        next_breaker = _maybe_open_breaker(
            current_level=next_level,
            red_cycles=r_cycles,
            prev_level=(r.escalation_level or "INFO"),
            prev_breaker=bool(r.breaker_open),
        )

        level_changed = next_level != (r.escalation_level or "INFO")
        breaker_changed = next_breaker != bool(r.breaker_open)

        if level_changed or breaker_changed:
            old_level = r.escalation_level or "INFO"
            r.escalation_level = next_level
            r.breaker_open = next_breaker
            r.last_notify_at = now
            r.save(update_fields=["escalation_level", "breaker_open", "last_notify_at", "updated_at"])
            updated += 1

            # Build payload (include last failed error_code, if any)
            payload: Dict[str, object] = {
                "title": "Escalation level changed",
                "symbol": sym,
                "timeframe": tf,
                "freshness_state": freshness,
                "analyses_ok_5m": int(r.analyses_ok_5m or 0),
                "analyses_fail_5m": fails_5m,
                "median_latency_ms": int(r.median_latency_ms or 0),
                "green_cycles": g_cycles,
                "amber_cycles": a_cycles,
                "red_cycles": r_cycles,
                "provider": r.provider,
                "fallback_active": bool(r.fallback_active),
                "key_age_days": r.key_age_days,
                "old_level": old_level,
                "new_level": next_level,
                "breaker_open": next_breaker,
                "ts": now.isoformat(),
            }

            last_err = _get_last_failed_error_code(sym, tf)
            if last_err:
                payload["error_code"] = last_err  # e.g., ErrorCode.ANALYSIS_ERR / INGESTION_TIMEOUT / UNKNOWN

            # Use next_level as notification severity
            try:
                send_notification(
                    event="escalation.level_changed",
                    severity=next_level,
                    payload=payload,
                )
            except Exception as _notify_exc:  # don't let notify failures break the task
                # Best-effort logging; avoid import cycles by not using logging config here
                pass

    return updated


# Backward/compat alias for older beat entries that used the plural form
@shared_task(name="backend.tasks.escalation.evaluate_escalations")
def evaluate_escalations() -> int:
    return evaluate_escalation()


@shared_task(name="backend.tasks.escalation.circuit_breaker_tick")
def circuit_breaker_tick() -> int:
    """
    Periodic breaker maintenance: close breakers when conditions improve.
    Returns: number of rows updated.
    """
    IngestionStatus = apps.get_model("backend", "IngestionStatus")
    updated = 0
    now = timezone.now()

    rows = IngestionStatus.objects.filter(breaker_open=True).only(
        "symbol",
        "timeframe",
        "freshness_state",
        "analyses_fail_5m",
        "escalation_level",
        "breaker_open",
        "provider",
    )

    for r in rows:
        sym = r.symbol
        tf = r.timeframe
        freshness = r.freshness_state or FRESH_RED
        fails_5m = int(r.analyses_fail_5m or 0)

        # Update counters (we need GREEN streaks to close)
        g_cycles, a_cycles, r_cycles = _update_counters(sym, tf, freshness)

        should_close = _maybe_close_breaker(
            breaker_open=bool(r.breaker_open),
            green_cycles=g_cycles,
            fails_5m=fails_5m,
        )

        if should_close:
            old_level = r.escalation_level or "INFO"
            r.breaker_open = False
            # when closing a breaker, level can de-escalate (but keep whatever evaluate_escalation will compute next)
            r.last_notify_at = now
            r.save(update_fields=["breaker_open", "last_notify_at", "updated_at"])
            updated += 1

            payload: Dict[str, object] = {
                "title": "Circuit breaker closed",
                "symbol": sym,
                "timeframe": tf,
                "freshness_state": freshness,
                "analyses_fail_5m": fails_5m,
                "green_cycles": g_cycles,
                "old_level": old_level,
                "breaker_open": False,
                "ts": now.isoformat(),
            }

            try:
                send_notification(
                    event="escalation.breaker_closed",
                    severity="INFO",
                    payload=payload,
                )
            except Exception:
                pass

    return updated
