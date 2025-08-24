# tests/test_agent0134_no_trade.py
# Ensures NO_TRADE decisions do NOT persist TradeAnalysis rows,
# while still writing transparent AnalysisLog entries.

import pytest
from django.utils import timezone

from backend.models import MarketData, MarketDataFeatures, TradeAnalysis, AnalysisLog
from backend.tasks import analysis_tasks


@pytest.mark.django_db
def test_no_trade_does_not_persist_and_logs(monkeypatch):
    symbol = "EURUSD"
    timeframe = "15m"

    # Seed a bar + features (pipeline would normally do this)
    bar_ts = timezone.now().replace(microsecond=0)
    md = MarketData.objects.create(
        symbol=symbol,
        timeframe=timeframe,
        timestamp=bar_ts,
        open=1.1000,
        high=1.1010,
        low=1.0990,
        close=1.1005,
        volume=1000.0,
        provider="AllTick",
    )
    MarketDataFeatures.objects.get_or_create(market_data=md)

    # Force rules to return NO_TRADE on the SAME bar_ts (idempotency key present)
    def fake_run_rules(sym, tf):
        assert sym == symbol and tf == timeframe
        return {
            "final_decision": "NO_TRADE",
            "rule_confidence": 0,
            "sl": None,
            "tp": None,
            "bar_ts": bar_ts,
        }

    monkeypatch.setattr(analysis_tasks.rules_bridge, "run_rules", fake_run_rules)

    # ML should not be required for NO_TRADE; keep a sentinel to ensure it isn't called
    sentinel = {"called": False}

    def fake_run_ml(sym, tf, bts):
        sentinel["called"] = True
        return {"confidence": 0}

    monkeypatch.setattr(analysis_tasks.ml_bridge, "run_ml", fake_run_ml)

    # Call analyze_latest N times; all should skip persistence
    N = 10
    for _ in range(N):
        res = analysis_tasks.analyze_latest(symbol, timeframe)
        # The task returns a skip payload for NO_TRADE
        assert isinstance(res, dict)
        assert res.get("skipped") == "no_trade"
        assert str(res.get("bar_ts")) in (str(bar_ts), bar_ts.isoformat())

    # DB assertions:
    # 1) Zero TradeAnalysis rows for this key (NO_TRADE contract)
    assert (
        TradeAnalysis.objects.filter(symbol=symbol, timeframe=timeframe, bar_ts=bar_ts).count() == 0
    ), "NO_TRADE must not persist TradeAnalysis rows"

    # 2) Exactly N AnalysisLog records written (transparent logging)
    logs = AnalysisLog.objects.filter(symbol=symbol, timeframe=timeframe, bar_ts=bar_ts)
    assert logs.count() == N, "Expected one AnalysisLog per NO_TRADE run"

    # Optional: ensure most recent log is COMPLETE (scheduler/task completed action)
    assert logs.order_by("-id").first().state == "COMPLETE"

    # Sanity: ML path was not required for NO_TRADE (task should early-return)
    assert sentinel["called"] is False
