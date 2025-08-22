from celery import shared_task
from django.db import transaction
from django.apps import apps

# IMPORTANT: import modules, not functions — enables pytest monkeypatch to work
import backend.rules.bridge as rules_bridge
import backend.ml.bridge as ml_bridge
from backend.analysis import composite as composite_mod
from backend.tasks.state_machine import (
    start_run,
    finish_run_ok,
    finish_run_fail,
    mark_tradeanalysis_status,
)


@shared_task
def analyze_latest(symbol: str, timeframe: str):
    MarketData = apps.get_model("backend", "MarketData")
    MarketDataFeatures = apps.get_model("backend", "MarketDataFeatures")
    TradeAnalysis = apps.get_model("backend", "TradeAnalysis")

    md = (
        MarketData.objects.filter(symbol=symbol, timeframe=timeframe)
        .order_by("-timestamp")
        .first()
    )
    if not md:
        return {"skipped": "no_marketdata"}

    # ensure features row exists (013.1 spine)
    mdf, _ = MarketDataFeatures.objects.get_or_create(market_data=md)

    # ---- Start run tracking ----
    log_id = start_run(symbol, timeframe, md.timestamp)

    ta_id = None
    try:
        # run rules
        r = rules_bridge.run_rules(symbol, timeframe)  # {'final_decision','rule_confidence','sl','tp','bar_ts'}
        if r.get("bar_ts") is None:
            finish_run_fail(log_id, "NO_BAR_TS", "Rules did not return bar_ts")
            return {"skipped": "no_bar_ts"}

        # NO_TRADE: log complete, DO NOT persist TradeAnalysis
        if r["final_decision"] == "NO_TRADE":
            finish_run_ok(log_id)
            return {"skipped": "no_trade"}

        # ML + composite
        ml_conf = ml_bridge.run_ml(symbol, timeframe, r["bar_ts"])
        comp = composite_mod.blend(r["rule_confidence"], ml_conf)

        # create TA (idempotent), mark COMPLETE
        with transaction.atomic():
            ta, _created = TradeAnalysis.objects.get_or_create(
                market_data_feature=mdf,
                timestamp=md.timestamp,
                defaults=dict(
                    final_decision=r["final_decision"],
                    rule_confidence_score=r["rule_confidence"],
                    ml_confidence=ml_conf,
                    composite_score=comp,
                    stop_loss=r.get("sl"),
                    take_profit=r.get("tp"),
                    ml_skipped=False,
                    status="PENDING",
                    started_at=md.timestamp,
                ),
            )
            ta_id = ta.id
            mark_tradeanalysis_status(ta_id, "COMPLETE")

        finish_run_ok(log_id)
        return {"id": ta_id, "ml_skipped": False}

    except Exception as e:
        # mark TA as FAILED if it exists or can be found
        if ta_id is None:
            ta_obj = (
                TradeAnalysis.objects.filter(
                    market_data_feature=mdf, timestamp=md.timestamp
                )
                .order_by("-id")
                .first()
            )
            if ta_obj:
                ta_id = ta_obj.id
        if ta_id is not None:
            mark_tradeanalysis_status(
                ta_id, "FAILED", error_code="ANALYSIS_ERR", error_message=str(e)
            )

        # always end the log with failure
        finish_run_fail(log_id, "ANALYSIS_ERR", str(e))
        return {"error": str(e)}
