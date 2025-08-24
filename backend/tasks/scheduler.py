# backend/tasks/scheduler.py
"""
013.4 Scheduler — Freshness Gating + Transparent Skips

Behavior
- Kicks a single ingestion beat each tick.
- For each (symbol, timeframe):
  • If breaker_open=True → skip analysis.
  • Compute freshness via is_fresh().
  • If GREEN → enqueue analyze_latest(symbol, timeframe).
  • If AMBER/RED → DO NOT enqueue; write an AnalysisLog row noting the skip,
    and call update_ingestion_status() so /api/ingestion/status reflects reality.

Notes
- We log AMBER/RED skips as AnalysisLog(state=COMPLETE) with an explanatory message.
  This avoids polluting TradeAnalysis while preserving an audit trail.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List

import yaml
from celery import shared_task
from django.utils import timezone

from backend.tasks.ingest_tasks import ingest_once
from backend.tasks.freshness import is_fresh, update_ingestion_status
from backend.tasks.analysis_tasks import analyze_latest
from backend.models import IngestionStatus, AnalysisLog, MarketData

logger = logging.getLogger(__name__)

WATCHLIST_PATH = Path("backend/orchestration/watchlist.yaml")


def _cfg() -> Dict[str, List[str]]:
    with WATCHLIST_PATH.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return {
        "pairs": list(data.get("pairs", [])),
        "timeframes": list(data.get("timeframes", [])),
    }


def _latest_bar_ts(symbol: str, timeframe: str):
    """
    Resolve the best bar_ts to attribute to a scheduler decision:
      1) IngestionStatus.last_bar_ts if present,
      2) else latest MarketData.timestamp if present,
      3) else 'now' (scheduler time).
    """
    st = IngestionStatus.objects.filter(symbol=symbol, timeframe=timeframe).first()
    if st and st.last_bar_ts:
        return st.last_bar_ts

    md = (
        MarketData.objects.filter(symbol=symbol, timeframe=timeframe)
        .order_by("-timestamp")
        .first()
    )
    if md:
        return md.timestamp

    return timezone.now()


@shared_task
def tick():
    """
    One scheduler tick:
      1) Trigger ingestion once (non-blocking).
      2) For each (symbol, timeframe):
         - Skip if breaker_open.
         - Freshness check.
         - If GREEN -> dispatch analysis.
         - If AMBER/RED -> write AnalysisLog entry explaining skip and
           refresh IngestionStatus (heartbeat + freshness numbers).
    """
    # 1) Kick ingestion
    try:
        ingest_once.delay()
    except Exception:  # defensive: don't let ingress failure stop scheduling loop
        logger.exception("Failed to dispatch ingest_once")

    # 2) Iterate watchlist
    cfg = _cfg()
    for sym in cfg["pairs"]:
        for tf in cfg["timeframes"]:
            # Circuit breaker check
            st = IngestionStatus.objects.filter(symbol=sym, timeframe=tf).first()
            if st and st.breaker_open:
                logger.info("Scheduler: breaker_open; skip %s %s", sym, tf)
                # Optional: log a skip entry as well to keep a visible audit
                _log_skip(sym, tf, reason="BREAKER_OPEN")
                continue

            fresh, _, color = is_fresh(sym, tf)

            if fresh and color == "GREEN":
                analyze_latest.delay(sym, tf)
            else:
                # Log a transparent skip in AnalysisLog
                _log_skip(sym, tf, reason=f"FRESHNESS_{color or 'UNKNOWN'}")
                # Ensure status/heartbeat are up-to-date for the UI
                try:
                    update_ingestion_status(sym, tf)
                except Exception:
                    logger.exception("update_ingestion_status failed for %s %s", sym, tf)


def _log_skip(symbol: str, timeframe: str, reason: str) -> None:
    """
    Write an AnalysisLog entry for scheduler decisions that intentionally skip analysis.
    We mark state=COMPLETE because the scheduler completed its decision successfully.
    """
    try:
        bar_ts = _latest_bar_ts(symbol, timeframe)
        AnalysisLog.objects.create(
            symbol=symbol,
            timeframe=timeframe,
            bar_ts=bar_ts,
            state="COMPLETE",
            finished_at=timezone.now(),
            error_message=f"SKIP: {reason}",
        )
    except Exception:
        logger.exception("Failed to write AnalysisLog skip for %s %s (%s)", symbol, timeframe, reason)
