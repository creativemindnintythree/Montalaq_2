# backend/tasks/analysis_hooks.py
"""
013.3 signal notification hook

- Triggers a "signal" notification when a TradeAnalysis finishes with status COMPLETE
  and the composite score meets/exceeds the configured threshold.
- Dedupes per (symbol, timeframe, bar_ts) using the IngestionStatus.last_signal_bar_ts
  field for cross-process safety (in addition to notify task's own cache-based dedupe).
"""

from __future__ import annotations

from typing import Optional

from django.conf import settings
from django.utils import timezone
from django.apps import apps

# Celery task (multi-channel) from notifications layer
from backend.tasks.notify import send_notification


def _get_models():
    IngestionStatus = apps.get_model("backend", "IngestionStatus")
    TradeAnalysis = apps.get_model("backend", "TradeAnalysis")
    return IngestionStatus, TradeAnalysis


def maybe_notify_signal(trade_analysis_obj) -> Optional[bool]:
    """
    Check a TradeAnalysis object and emit a single "signal" notification
    if all conditions are met. Returns:
      True  -> notification dispatched
      False -> conditions not met / deduped
      None  -> no-op due to missing context
    """
    IngestionStatus, TradeAnalysis = _get_models()

    ta = trade_analysis_obj
    if ta is None:
        return None

    # Require COMPLETE status and composite score present
    if getattr(ta, "status", None) != "COMPLETE":
        return False

    comp = getattr(ta, "composite_score", None)
    if comp is None:
        return False

    # Threshold from settings
    threshold = int(settings.NOTIFICATION_DEFAULTS.get("composite_notify_threshold", 70))
    if comp < threshold:
        return False

    # Pull symbol/timeframe/bar_ts from related MarketDataFeatures/MarketData
    mdf = getattr(ta, "market_data_feature", None)
    if not mdf or not getattr(mdf, "market_data", None):
        return None

    md = mdf.market_data
    symbol = getattr(md, "symbol", None)
    timeframe = getattr(md, "timeframe", None)
    bar_ts = getattr(ta, "timestamp", None) or getattr(md, "timestamp", None)

    if not symbol or not timeframe or not bar_ts:
        return None

    # Cross-process dedupe using IngestionStatus.last_signal_bar_ts
    status_row, _ = IngestionStatus.objects.get_or_create(symbol=symbol, timeframe=timeframe)
    if status_row.last_signal_bar_ts == bar_ts:
        return False  # already notified this bar

    # Build payload
    payload = {
        "title": "Trade signal",
        "symbol": symbol,
        "timeframe": timeframe,
        "bar_ts": bar_ts,
        "decision": getattr(ta, "final_decision", None),
        "composite": comp,
        "sl": getattr(ta, "stop_loss", None) or getattr(ta, "sl", None),
        "tp": getattr(ta, "take_profit", None) or getattr(ta, "tp", None),
        # Optionally include explainability slice if present
        "top_features": getattr(ta, "top_features", None),
    }

    # Dispatch async notification (notify task also has cache-based dedupe)
    send_notification.delay(event="signal", severity="INFO", payload=payload)

    # Persist dedupe marker + heartbeat
    status_row.last_signal_bar_ts = bar_ts
    status_row.last_notify_at = timezone.now()
    status_row.save(update_fields=["last_signal_bar_ts", "last_notify_at"])

    return True
