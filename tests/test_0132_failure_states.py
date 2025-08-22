# tests/test_0132_failure_states.py
import uuid
import pytest
from django.utils import timezone
from django.apps import apps

# We will monkeypatch backend.rules.bridge.run_rules and backend.ml.bridge.run_ml
# to drive the pipeline into specific branches (NO_TRADE, exception).
# Expectations (per 013.2 state machine):
#  - If ML raises before a TradeAnalysis exists → AnalysisLog=FAILED, no TradeAnalysis row created/updated.
#  - If NO_TRADE → AnalysisLog=COMPLETE, no TradeAnalysis row created.
#  - If a TradeAnalysis already exists for that (mdf, ts) and ML raises →
#       the TA should be marked FAILED (error_code set), and AnalysisLog=FAILED.
#
# Options for test isolation:
#  Option A (enabled): use a unique symbol per test via UUID to avoid cross-test interference.
#  Option B (optional): if you later add a scoped analysis entrypoint, you could call that instead.
#                       Current tests call analyze_latest() directly (sync), which is fine.


@pytest.mark.django_db
def test_no_trade_logs_complete_and_creates_no_ta(monkeypatch):
    MarketData = apps.get_model("backend", "MarketData")
    MarketDataFeatures = apps.get_model("backend", "MarketDataFeatures")
    TradeAnalysis = apps.get_model("backend", "TradeAnalysis")
    AnalysisLog = apps.get_model("backend", "AnalysisLog")
    from backend.tasks.analysis_tasks import analyze_latest

    # ---- Option A: isolate symbol ----
    symbol = f"EURUSD_NOTRADE_{uuid.uuid4().hex[:6]}"
    timeframe = "1m"
    ts = timezone.now()

    # Seed a bar
    md = MarketData.objects.create(
        symbol=symbol,
        timeframe=timeframe,
        timestamp=ts,
        open=1.0, high=1.0, low=1.0, close=1.0,
        volume=0.0,
        provider="AllTick",
    )
    # Ensure features row (analysis task would do this too)
    MarketDataFeatures.objects.get_or_create(market_data=md)

    # Monkeypatch rules → NO_TRADE with a valid bar_ts
    def fake_rules(sym, tf):
        assert sym == symbol and tf == timeframe
        return {"final_decision": "NO_TRADE", "rule_confidence": 42, "sl": None, "tp": None, "bar_ts": ts}

    monkeypatch.setattr("backend.rules.bridge.run_rules", fake_rules)

    # Run analyze
    out = analyze_latest(symbol, timeframe)
    assert out.get("skipped") == "no_trade"

    # AnalysisLog should have COMPLETE
    log = AnalysisLog.objects.order_by("-id").first()
    assert log is not None
    assert log.state == "COMPLETE"

    # No TradeAnalysis row should exist
    assert TradeAnalysis.objects.count() == 0


@pytest.mark.django_db
def test_ml_exception_logs_failed_and_no_ta_when_not_created(monkeypatch):
    MarketData = apps.get_model("backend", "MarketData")
    MarketDataFeatures = apps.get_model("backend", "MarketDataFeatures")
    TradeAnalysis = apps.get_model("backend", "TradeAnalysis")
    AnalysisLog = apps.get_model("backend", "AnalysisLog")
    from backend.tasks.analysis_tasks import analyze_latest

    # ---- Option A: isolate symbol ----
    symbol = f"EURUSD_MLFAILNEW_{uuid.uuid4().hex[:6]}"
    timeframe = "1m"
    ts = timezone.now()

    # Seed a bar
    md = MarketData.objects.create(
        symbol=symbol,
        timeframe=timeframe,
        timestamp=ts,
        open=1.0, high=1.0, low=1.0, close=1.0,
        volume=0.0,
        provider="AllTick",
    )
    MarketDataFeatures.objects.get_or_create(market_data=md)

    # Rules → trade signal (so ML is attempted)
    def fake_rules(sym, tf):
        return {"final_decision": "LONG", "rule_confidence": 60, "sl": 0.9, "tp": 1.1, "bar_ts": ts}

    # ML → raise (before TA is created)
    def fake_ml(sym, tf, bar_ts):
        raise RuntimeError("boom")

    monkeypatch.setattr("backend.rules.bridge.run_rules", fake_rules)
    monkeypatch.setattr("backend.ml.bridge.run_ml", fake_ml)

    out = analyze_latest(symbol, timeframe)
    assert "error" in out

    # AnalysisLog should be FAILED
    log = AnalysisLog.objects.order_by("-id").first()
    assert log is not None
    assert log.state == "FAILED"
    assert "boom" in (log.error_message or "")

    # No TradeAnalysis row should exist (since ML failed before creation)
    assert TradeAnalysis.objects.count() == 0


@pytest.mark.django_db
def test_ml_exception_marks_existing_ta_failed(monkeypatch):
    """
    If a TradeAnalysis already exists for (mdf, ts) and ML raises later,
    the except-block should locate and mark that TA as FAILED.
    """
    MarketData = apps.get_model("backend", "MarketData")
    MarketDataFeatures = apps.get_model("backend", "MarketDataFeatures")
    TradeAnalysis = apps.get_model("backend", "TradeAnalysis")
    AnalysisLog = apps.get_model("backend", "AnalysisLog")
    from backend.tasks.analysis_tasks import analyze_latest

    # ---- Option A: isolate symbol ----
    symbol = f"EURUSD_MLFAILEXIST_{uuid.uuid4().hex[:6]}"
    timeframe = "1m"
    ts = timezone.now()

    # Seed a bar + features
    md = MarketData.objects.create(
        symbol=symbol,
        timeframe=timeframe,
        timestamp=ts,
        open=1.0, high=1.0, low=1.0, close=1.0,
        volume=0.0,
        provider="AllTick",
    )
    mdf, _ = MarketDataFeatures.objects.get_or_create(market_data=md)

    # Pre-create a TA row as if a previous attempt created it (e.g., retry scenario)
    ta = TradeAnalysis.objects.create(
        market_data_feature=mdf,
        timestamp=ts,
        final_decision="LONG",
        rule_confidence_score=55,
        status="PENDING",
        started_at=ts,
    )

    # Rules → trade signal (so ML is attempted)
    def fake_rules(sym, tf):
        return {"final_decision": "LONG", "rule_confidence": 55, "sl": 0.9, "tp": 1.1, "bar_ts": ts}

    # ML → raise
    def fake_ml(sym, tf, bar_ts):
        raise RuntimeError("model failed to score")

    monkeypatch.setattr("backend.rules.bridge.run_rules", fake_rules)
    monkeypatch.setattr("backend.ml.bridge.run_ml", fake_ml)

    out = analyze_latest(symbol, timeframe)
    assert "error" in out

    # The existing TA should be marked FAILED
    ta.refresh_from_db()
    assert ta.status == "FAILED"
    assert ta.error_code == "ANALYSIS_ERR"
    assert "model failed to score" in (ta.error_message or "")

    # AnalysisLog should be FAILED
    log = AnalysisLog.objects.order_by("-id").first()
    assert log is not None and log.state == "FAILED"
