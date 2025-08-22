from celery import shared_task
import yaml

from backend.tasks.ingest_tasks import ingest_once
from backend.tasks.freshness import is_fresh, update_ingestion_status
from backend.tasks.analysis_tasks import analyze_latest


def _cfg():
    with open("backend/orchestration/watchlist.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


@shared_task
def tick():
    """
    One scheduler tick:
      1) Trigger ingestion once.
      2) For each (symbol, timeframe):
         - Check freshness.
         - If GREEN -> dispatch analysis.
         - If AMBER/RED -> just update IngestionStatus (no analysis).
    """
    ingest_once.delay()

    cfg = _cfg()
    for sym in cfg["pairs"]:
        for tf in cfg["timeframes"]:
            fresh, _, color = is_fresh(sym, tf)
            if fresh and color == "GREEN":
                analyze_latest.delay(sym, tf)
            else:
                # Ensure IngestionStatus reflects AMBER/RED state even if we skip analysis
                update_ingestion_status(sym, tf)
