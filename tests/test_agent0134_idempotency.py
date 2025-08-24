# tests/test_agent0134_idempotency.py
# Ensures duplicates are blocked for the same (symbol, timeframe, bar_ts)
# Contract:
#   - Replaying the same tick twice must NOT create a second TradeAnalysis row.
#   - analyze_latest() returns created=True for first run, created=False for subsequent runs.

import pytest
from django.utils import timezone

from backend.models import MarketData, MarketDataFeatures, TradeAnalysis
from backend.tasks import analysis_tasks


@pytest.mark.django_db
def test_idempotent_tradeanalysis_no_duplicates(monkeypatch):
    symbol = "EURUSD"
    timeframe = "15m"

    # Prepare a canonical bar (and features row) for the test
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
    # Features row (pipeline normally creates this; we ensure it's present)
    MarketDataFeatures.objects.get_or_create(market_data=md)

    # --- Monkeypatch rules / ML / composite to be deterministic ---
    def fake_run_rules(sym, tf):
        assert sym == symbol and tf == timeframe
        return {
            "final_decision": "LONG",
            "rule_confidence": 70,
            "sl": 1.0980,
            "tp": 1.1030,
            "bar_ts": bar_ts,  # CRITICAL for idempotency key
        }

    monkeypatch.setattr(analysis_tasks.rules_bridge, "run_rules", fake_run_rules)

    def fake_run_ml(sym, tf, bts):
        assert (sym, tf, bts) == (symbol, timeframe, bar_ts)
        return {"confidence": 55}

    monkeypatch.setattr(analysis_tasks.ml_bridge, "run_ml", fake_run_ml)

    def fake_blend(rule_conf, ml_conf):
        # simple average, returns float
        return (float(rule_conf) + float(ml_conf)) / 2.0

    monkeypatch.setattr(analysis_tasks.composite_mod, "blend", fake_blend)

    # --- Execute analyze_latest twice for the same (symbol, timeframe, bar_ts) ---
    res1 = analysis_tasks.analyze_latest(symbol, timeframe)
    res2 = analysis_tasks.analyze_latest(symbol, timeframe)

    # First call should create the row; second should reuse it (no duplicate)
    assert isinstance(res1, dict) and isinstance(res2, dict)
    assert res1.get("created") is True
    assert res2.get("created") is False

    # DB-level assertion: exactly one row exists for the idempotent key
    qs = TradeAnalysis.objects.filter(symbol=symbol, timeframe=timeframe, bar_ts=bar_ts)
    assert qs.count() == 1, "Expected a single TradeAnalysis row for the idempotent key"

    ta = qs.first()
    # Sanity checks — fields persisted and sensible
    assert ta.final_decision == "LONG"
    assert ta.rule_confidence_score == 70
    assert ta.sl == pytest.approx(1.0980)
    assert ta.tp == pytest.approx(1.1030)
    # composite derived from 70 (rules) and 55 (ml)
    assert ta.composite_score == pytest.approx((70 + 55) / 2.0)
