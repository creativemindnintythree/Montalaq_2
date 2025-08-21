from celery import shared_task
from backend.tasks.ingest_tasks import ingest_once
from backend.tasks.freshness import is_fresh
from backend.tasks.analysis_tasks import analyze_latest
import yaml

def _cfg():
    with open("backend/orchestration/watchlist.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

@shared_task
def tick():
    ingest_once.delay()
    cfg = _cfg()
    for sym in cfg["pairs"]:
        for tf in cfg["timeframes"]:
            fresh, _, _ = is_fresh(sym, tf)
            if fresh:
                analyze_latest.delay(sym, tf)
