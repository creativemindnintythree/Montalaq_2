import time
from django.utils import timezone
from django.apps import apps


def start_run(symbol: str, timeframe: str, bar_ts):
    """
    Create a new AnalysisLog entry in PENDING state and return its ID + start_time.
    """
    AnalysisLog = apps.get_model("backend", "AnalysisLog")
    log = AnalysisLog.objects.create(
        symbol=symbol,
        timeframe=timeframe,
        bar_ts=bar_ts,
        state="PENDING",
        started_at=timezone.now(),
    )
    return log.id


def finish_run_ok(log_id: int):
    """
    Mark AnalysisLog entry as COMPLETE, set finished_at and latency.
    """
    AnalysisLog = apps.get_model("backend", "AnalysisLog")
    try:
        log = AnalysisLog.objects.get(id=log_id)
    except AnalysisLog.DoesNotExist:
        return None

    log.state = "COMPLETE"
    log.finished_at = timezone.now()
    if log.started_at:
        delta = log.finished_at - log.started_at
        log.latency_ms = int(delta.total_seconds() * 1000)
    log.save(update_fields=["state", "finished_at", "latency_ms"])
    return log


def finish_run_fail(log_id: int, code: str, msg: str):
    """
    Mark AnalysisLog entry as FAILED, set error details and latency.
    """
    AnalysisLog = apps.get_model("backend", "AnalysisLog")
    try:
        log = AnalysisLog.objects.get(id=log_id)
    except AnalysisLog.DoesNotExist:
        return None

    log.state = "FAILED"
    log.finished_at = timezone.now()
    if log.started_at:
        delta = log.finished_at - log.started_at
        log.latency_ms = int(delta.total_seconds() * 1000)
    log.error_code = code
    log.error_message = msg
    log.save(update_fields=["state", "finished_at", "latency_ms", "error_code", "error_message"])
    return log


def mark_tradeanalysis_status(trade_id: int, status: str, error_code: str = None, error_message: str = None):
    """
    Update TradeAnalysis row with new status + optional error details.
    """
    TradeAnalysis = apps.get_model("backend", "TradeAnalysis")
    try:
        ta = TradeAnalysis.objects.get(id=trade_id)
    except TradeAnalysis.DoesNotExist:
        return None

    ta.status = status
    ta.finished_at = timezone.now()
    if status == "FAILED":
        ta.error_code = error_code
        ta.error_message = error_message
    if status == "PENDING":
        ta.started_at = timezone.now()
    ta.save(update_fields=["status", "finished_at", "error_code", "error_message", "started_at"])
    return ta
