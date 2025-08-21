from celery import shared_task
from django.apps import apps

@shared_task
def ensure_features_for_latest(symbol: str, timeframe: str):
    MarketData = apps.get_model("backend", "MarketData")
    MarketDataFeatures = apps.get_model("backend", "MarketDataFeatures")
    md = (MarketData.objects
          .filter(symbol=symbol, timeframe=timeframe)
          .order_by("-timestamp")
          .first())
    if not md:
        return {"skipped": "no_marketdata"}
    MarketDataFeatures.objects.get_or_create(market_data=md)
    return {"ok": True, "ts": md.timestamp}
