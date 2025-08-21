from django.utils import timezone
from django.apps import apps
import yaml

def _cfg():
    with open("backend/orchestration/watchlist.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def is_fresh(symbol: str, timeframe: str):
    MarketData = apps.get_model("backend", "MarketData")
    cfg = _cfg()
    th = cfg["freshness_seconds"][timeframe]
    last = (MarketData.objects
            .filter(symbol=symbol, timeframe=timeframe)
            .order_by("-timestamp").first())
    if not last: return (False, None, "RED")
    age = (timezone.now() - last.timestamp).total_seconds()
    if age <= th: return (True, last.timestamp, "GREEN")
    if age <= 3 * th: return (False, last.timestamp, "AMBER")
    return (False, last.timestamp, "RED")
