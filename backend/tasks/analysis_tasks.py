from celery import shared_task
from django.db import transaction
from django.apps import apps
from backend.tasks.feature_tasks import ensure_features_for_latest
from backend.rules.bridge import run_rules
from backend.ml.bridge import run_ml
from backend.analysis.composite import blend

@shared_task
def analyze_latest(symbol: str, timeframe: str):
    MarketData = apps.get_model("backend", "MarketData")
    MarketDataFeatures = apps.get_model("backend", "MarketDataFeatures")
    TradeAnalysis = apps.get_model("backend", "TradeAnalysis")

    md = (MarketData.objects
          .filter(symbol=symbol, timeframe=timeframe)
          .order_by("-timestamp").first())
    if not md:
        return {"skipped": "no_marketdata"}

    # ensure features row exists (013.1 spine)
    mdf, _ = MarketDataFeatures.objects.get_or_create(market_data=md)

    r = run_rules(symbol, timeframe)  # {'final_decision','rule_confidence','sl','tp','bar_ts'}
    if r["bar_ts"] is None:
        return {"skipped": "no_bar_ts"}

    if r["final_decision"] == "NO_TRADE":
        with transaction.atomic():
            ta, _ = TradeAnalysis.objects.get_or_create(
                market_data_feature=mdf, timestamp=md.timestamp,
                defaults=dict(
                    final_decision="NO_TRADE",
                    rule_confidence_score=r["rule_confidence"],
                    ml_skipped=True,
                )
            )
        return {"id": ta.id, "ml_skipped": True}

    ml_conf = run_ml(symbol, timeframe, r["bar_ts"])
    comp = blend(r["rule_confidence"], ml_conf)

    with transaction.atomic():
        ta, _ = TradeAnalysis.objects.get_or_create(
            market_data_feature=mdf, timestamp=md.timestamp,
            defaults=dict(
                final_decision=r["final_decision"],
                rule_confidence_score=r["rule_confidence"],
                ml_confidence=ml_conf,
                composite_score=comp,
                # SL/TP stay per 010 defaults; dynamic later
                stop_loss=r.get("sl"), take_profit=r.get("tp"),
                ml_skipped=False,
            )
        )
    return {"id": ta.id, "ml_skipped": False}
