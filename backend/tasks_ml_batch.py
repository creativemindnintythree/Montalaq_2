from datetime import timedelta
import logging
from django.utils import timezone
from django.db.models import Q
from celery import shared_task

from backend.models import TradeAnalysis
from ml_pipeline import config as ml_cfg
from celery_tasks.run_ml_on_new_data import run_ml_on_new_data

logger = logging.getLogger(__name__)

# TEMPORARY bridge (Agent 011.3) — kept until Agent 013 delivers orchestration
@shared_task(name="ml.batch_run_recent")
def batch_run_recent(limit: int = 50, minutes: int = 10) -> int:
    """
    Batch runner for recent TradeAnalysis rows.
    - Selects rows within the last `minutes` window (by timestamp or created_at).
    - Excludes NO_TRADE decisions.
    - Runs ML pipeline on each TA.id.

    Returns: number of processed rows.
    """
    since = timezone.now() - timedelta(minutes=minutes)

    qs = (
        TradeAnalysis.objects
        .filter(Q(timestamp__gte=since) | Q(timestamp__isnull=True, created_at__gte=since))
        .exclude(final_decision=ml_cfg.SIGNAL_NO_TRADE)
        .order_by("-timestamp", "-created_at")[:limit]
    )

    count = 0
    for ta in qs:
        try:
            run_ml_on_new_data(ta.id)
            logger.debug("[Agent011.3] batch-run TA=%s completed", ta.id)
            count += 1
        except Exception as e:
            logger.error("[Agent011.3] batch-run failed TA=%s err=%s", ta.id, str(e), exc_info=True)

    logger.info(
        "[Agent011.3] batch_run_recent processed=%d lookback_min=%d limit=%d",
        count, minutes, limit
    )

    if count == 0:
        logger.warning("[Agent011.3] batch_run_recent no trades found in last %d minutes", minutes)

    return count
