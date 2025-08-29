import random, time
from django.db.utils import OperationalError
# backend/tasks/analysis_tasks.py
"""
013.4 analyze task — Idempotency + NO_TRADE discipline

What this does now:
- Uses rules → (optionally) ML → composite, same spine as 013.1/013.3.
- STARTS an AnalysisLog run and FINISHES it (ok/fail) via state_machine helpers.
- If rules decide NO_TRADE:
    ✅ Finish AnalysisLog as COMPLETE
    ❌ Do NOT persist a TradeAnalysis row
- If rules decide LONG/SHORT:
    ✅ Persist TradeAnalysis idempotently with get_or_create on (symbol,timeframe,bar_ts)
- Links TradeAnalysis to the correct MarketDataFeatures row for the analyzed bar_ts.
- Uses model-level finish_run_fail for consistent error taxonomy (013.2.1).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from celery import shared_task
from django.apps import apps
from django.db import transaction

# Import modules (not functions) so pytest monkeypatching can replace them cleanly
import backend.rules.bridge as rules_bridge
import backend.ml.bridge as ml_bridge
from backend.analysis import composite as composite_mod
from backend.tasks.state_machine import (
    start_run,
    finish_run_ok,
    finish_run_fail,
    mark_tradeanalysis_status,
)

# Centralized error taxonomy (013.2.1)
from backend.errors import ErrorCode, EXCEPTION_MAP  # noqa: F401

logger = logging.getLogger(__name__)


def _extract_ml_confidence(ml_out: Any) -> float:
    """
    Accept either a float (legacy) or a dict (new) from ml_bridge.run_ml().
    Returns a float 0..100.
    """
    if isinstance(ml_out, (int, float)):
        return float(ml_out)
    if isinstance(ml_out, dict):
        # Common keys: 'confidence', 'ml_confidence'
        for k in ("confidence", "ml_confidence"):
            if k in ml_out and isinstance(ml_out[k], (int, float)):
                return float(ml_out[k])
    # Fallback
    try:
        return float(ml_out)  # may raise
    except Exception:
        return 0.0


@shared_task
def analyze_latest(symbol: str, timeframe: str) -> Dict[str, Any]:
    """
    Analyze the latest bar for (symbol, timeframe).

    Flow:
      1) Find the latest MarketData bar_ts.
      2) Run rules for (symbol,timeframe). Must return {'final_decision','rule_confidence','sl','tp','bar_ts'}.
         - If NO_TRADE: close AnalysisLog OK and return without writing TradeAnalysis.
      3) Run ML and blend composite.
      4) get_or_create TradeAnalysis on (symbol,timeframe,bar_ts) for hard idempotency.
      5) Mark COMPLETE and close AnalysisLog OK.

    On any exception:
      - If a TradeAnalysis row was/should be present, call ta.finish_run_fail(exc).
      - Always close the AnalysisLog with failure, mapped to canonical ErrorCode.
    """
    MarketData = apps.get_model("backend", "MarketData")
    MarketDataFeatures = apps.get_model("backend", "MarketDataFeatures")
    TradeAnalysis = apps.get_model("backend", "TradeAnalysis")

    # 1) Latest bar for the pair (still used for feature row bootstrap / fallback)
    md = (
        MarketData.objects.filter(symbol=symbol, timeframe=timeframe)
        .order_by("-timestamp")
        .first()
    )
    if not md:
        logger.info("analyze_latest: no MarketData for %s %s", symbol, timeframe)
        return {"skipped": "no_marketdata"}

    # Bootstrap a features row for the latest bar (keeps 013.1 spine intact);
    # we will re-point to the exact bar_ts later if rules specify a different candle.
    mdf_latest, _ = MarketDataFeatures.objects.get_or_create(market_data=md)

    # ---- Start AnalysisLog (use the most precise bar_ts when available) ----
    # We will first start with the latest md.timestamp; if rules supply bar_ts, we’ll adjust the log end only.
    log_id = start_run(symbol, timeframe, md.timestamp)

    ta_obj = None
    try:
        # 2) RULES
        r: Dict[str, Any] = rules_bridge.run_rules(symbol, timeframe)
        bar_ts = r.get("bar_ts")  # REQUIRED for idempotency key

        if bar_ts is None:
            finish_run_fail(log_id, ErrorCode.UNKNOWN.value, "Rules returned no bar_ts")
            return {"skipped": "no_bar_ts"}

        final_decision = r.get("final_decision")
        rule_conf = r.get("rule_confidence")
        sl = r.get("sl")
        tp = r.get("tp")

        if final_decision == "NO_TRADE":
            # 013.4 discipline: log-only, no DB persistence into TradeAnalysis
            finish_run_ok(log_id)
            return {"skipped": "no_trade", "bar_ts": str(bar_ts)}

        # 3) ML + COMPOSITE
        ml_out = ml_bridge.run_ml(symbol, timeframe, bar_ts)
        ml_conf = _extract_ml_confidence(ml_out)
        composite = composite_mod.blend(rule_conf, ml_conf)

        # Find (or create) the exact features row that matches bar_ts
        md_exact = (
            MarketData.objects.filter(symbol=symbol, timeframe=timeframe, timestamp=bar_ts)
            .first()
        )
        # Fall back to latest if we do not have the exact bar in MarketData (should be rare)
        mdf_for_bar: Optional[models.Model] = None  # type: ignore[name-defined]
        if md_exact:
            mdf_for_bar, _ = MarketDataFeatures.objects.get_or_create(market_data=md_exact)
        else:
            mdf_for_bar = mdf_latest

        # 4) Persist idempotently — get_or_create on (symbol, timeframe, bar_ts)
        with transaction.atomic():
            ta_obj, created = TradeAnalysis.objects.get_or_create(
                symbol=symbol,
                timeframe=timeframe,
                bar_ts=bar_ts,
                defaults=dict(
                    market_data_feature=mdf_for_bar,
                    final_decision=final_decision,
                    rule_confidence_score=rule_conf,
                    sl=sl,
                    tp=tp,
                    ml_confidence=ml_conf,
                    composite_score=composite,
                    ml_skipped=False,
                    status="PENDING",
                    started_at=bar_ts,
                ),
            )

            # If it already existed, update mutable output fields (idempotent upsert)
            if not created:
                # only update if any value changed to avoid noisy writes
                fields_to_update = []
                if ta_obj.market_data_feature_id != getattr(mdf_for_bar, "id", None):
                    ta_obj.market_data_feature = mdf_for_bar
                    fields_to_update.append("market_data_feature")
                if ta_obj.final_decision != final_decision:
                    ta_obj.final_decision = final_decision
                    fields_to_update.append("final_decision")
                if ta_obj.rule_confidence_score != rule_conf:
                    ta_obj.rule_confidence_score = rule_conf
                    fields_to_update.append("rule_confidence_score")
                if ta_obj.sl != sl:
                    ta_obj.sl = sl
                    fields_to_update.append("sl")
                if ta_obj.tp != tp:
                    ta_obj.tp = tp
                    fields_to_update.append("tp")
                if ta_obj.ml_confidence != ml_conf:
                    ta_obj.ml_confidence = ml_conf
                    fields_to_update.append("ml_confidence")
                if ta_obj.composite_score != composite:
                    ta_obj.composite_score = composite
                    fields_to_update.append("composite_score")
                if fields_to_update:
                    _save_with_retry(ta_obj, update_fields=fields_to_update + ["updated_at"])

            # Mark COMPLETE via state machine helper
            mark_tradeanalysis_status(ta_obj.id, "COMPLETE")

        # 5) Close log OK
        finish_run_ok(log_id)
        return {"id": ta_obj.id, "created": created, "ml_skipped": False}

    except Exception as exc:  # noqa: BLE001 — task boundary, contain all failures
        # Map to canonical error code per 013.2.1
        mapped = EXCEPTION_MAP.get(type(exc), ErrorCode.UNKNOWN)

        # If we didn't create a TA row, try to find it by idempotent key
        if ta_obj is None:
            try:
                ta_obj = (
                    TradeAnalysis.objects.filter(symbol=symbol, timeframe=timeframe, bar_ts=md.timestamp)
                    .order_by("-id")
                    .first()
                )
            except Exception:
                ta_obj = None

        if ta_obj is not None:
            # Delegate failure persistence to the model helper (writes status/error/finished_at)
            try:
                ta_obj.finish_run_fail(exc)
            except Exception:
                logger.exception("finish_run_fail model hook raised")

        # Always end the AnalysisLog with failure
        finish_run_fail(log_id, mapped.value, str(exc))
        return {"error": str(exc), "error_code": mapped.value}
def _save_with_retry(obj, update_fields=None, attempts=6, base=0.05):
    """Retry ORM save on SQLite lock with exponential backoff + jitter."""
    for i in range(attempts):
        try:
            _save_with_retry(obj, update_fields=update_fields)
            return
        except OperationalError as e:
            m = str(e).lower()
            if "database is locked" not in m and "database is busy" not in m:
                raise
            time.sleep(base * (2 ** i) + random.uniform(0, base))
    _save_with_retry(obj, update_fields=update_fields)
