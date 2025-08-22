# backend/tasks/utils.py
import yaml
from django.db import transaction
from backend.models import MarketData


def parse_watchlist(path: str = "backend/orchestration/watchlist.yaml") -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


@transaction.atomic
def upsert_market_bar(bar: dict):
    """
    Idempotent write on (symbol, timeframe, timestamp) to MarketData.
    Only persist fields that actually belong to MarketData.
    """
    allowed = {
        "open",
        "high",
        "low",
        "close",
        "volume",
        "provider",
    }
    defaults = {k: v for k, v in bar.items() if k in allowed}

    MarketData.objects.update_or_create(
        symbol=bar["symbol"],
        timeframe=bar["timeframe"],
        timestamp=bar["timestamp"],
        defaults=defaults,
    )
