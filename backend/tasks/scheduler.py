from __future__ import annotations
from django.utils import timezone
import logging
from celery import shared_task
from django.apps import apps

from backend.tasks.analysis_tasks import analyze_latest
from backend.tasks.ingest_tasks import ingest_once
from backend.tasks import freshness as freshness_mod

logger = logging.getLogger(__name__)


def _cfg():
    # Centralized watchlist; keep in sync with your env/config as needed
    return {
        "pairs": ["EURUSD", "GBPUSD"],
        "timeframes": ["1m", "15m"],
    }


def _log_skip(symbol: str, timeframe: str, reason: str):
    """Persist a skip entry via AnalysisLog for transparency."""
    AnalysisLog = apps.get_model("backend", "AnalysisLog")
    try:
        AnalysisLog.objects.create(
            symbol=symbol,
            timeframe=timeframe,
            bar_ts=timezone.now(),
            error_message=f"SKIP: {reason}",
        )
    except Exception:
        logger.exception("Failed to log skip for %s %s: %s", symbol, timeframe, reason)
@shared_task
def tick():
    """Kick ingestion once, then iterate pairs/timeframes.
    - Skip only the pair/timeframe with breaker_open
    - If freshness not GREEN, update status and log a skip
    - If GREEN, enqueue analysis
    """
    # 1) Kick ingestion (defensive)
    try:
        ingest_once.delay()
    except Exception:
        logger.exception("Failed to dispatch ingest_once")

    # 2) Iterate configured pairs/timeframes
    cfg = _cfg()
    IngestionStatus = apps.get_model("backend", "IngestionStatus")

    for sym in cfg["pairs"]:
        for tf in cfg["timeframes"]:
            # Circuit breaker check
            st = IngestionStatus.objects.filter(symbol=sym, timeframe=tf).first()
            if st and getattr(st, "breaker_open", False):
                logger.info("Scheduler: breaker_open; skip %s %s", sym, tf)
                _log_skip(sym, tf, reason="BREAKER_OPEN")
                continue

            # Freshness check
            fresh, _, color = freshness_mod.is_fresh(sym, tf)
            if fresh and color == "GREEN":
                analyze_latest.delay(sym, tf)
            else:
                _log_skip(sym, tf, reason=f"FRESHNESS_{color or 'UNKNOWN'}")
                try:
                    freshness_mod.update_ingestion_status(sym, tf)
                except Exception:
                    logger.exception("update_ingestion_status failed for %s %s", sym, tf)

