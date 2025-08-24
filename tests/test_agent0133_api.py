# tests/test_agent0133_api.py
import uuid
import json
import pytest
from django.test import Client
from django.utils import timezone
from django.apps import apps


@pytest.mark.django_db
def test_latest_400_missing_params():
    c = Client()

    # Missing both
    r = c.get("/api/analysis/latest")
    assert r.status_code == 400

    # Missing tf
    r = c.get("/api/analysis/latest", {"pair": "EURUSD"})
    assert r.status_code == 400

    # Missing pair
    r = c.get("/api/analysis/latest", {"tf": "1m"})
    assert r.status_code == 400


@pytest.mark.django_db
def test_history_400_missing_params():
    c = Client()

    # Missing both
    r = c.get("/api/analysis/history")
    assert r.status_code == 400

    # Missing tf
    r = c.get("/api/analysis/history", {"pair": "EURUSD"})
    assert r.status_code == 400

    # Missing pair
    r = c.get("/api/analysis/history", {"tf": "1m"})
    assert r.status_code == 400


@pytest.mark.django_db
def test_latest_returns_single_analysis_record_fields():
    """
    Create a single TradeAnalysis record and verify /api/analysis/latest returns it,
    including the public fields expected by 013.3 serializers.
    """
    MarketData = apps.get_model("backend", "MarketData")
    MarketDataFeatures = apps.get_model("backend", "MarketDataFeatures")
    TradeAnalysis = apps.get_model("backend", "TradeAnalysis")

    c = Client()

    symbol = f"EURUSD_{uuid.uuid4().hex[:6]}"
    tf = "1m"
    ts = timezone.now()

    md = MarketData.objects.create(
        symbol=symbol,
        timeframe=tf,
        timestamp=ts,
        open=1.0,
        high=1.0,
        low=1.0,
        close=1.0,
        volume=0.0,
        provider="AllTick",
    )
    mdf, _ = MarketDataFeatures.objects.get_or_create(market_data=md)

    ta = TradeAnalysis.objects.create(
        market_data_feature=mdf,
        timestamp=ts,
        final_decision="LONG",
        rule_confidence_score=66,
        ml_confidence=72,
        composite_score=70,
        stop_loss=0.95,
        take_profit=1.05,
        status="COMPLETE",
        started_at=ts,
        error_code=None,
        error_message=None,
    )

    r = c.get("/api/analysis/latest", {"pair": symbol, "tf": tf})
    assert r.status_code == 200, r.content

    data = json.loads(r.content.decode("utf-8"))
    # Required keys (013.3 serializer contract)
    for k in [
        "symbol",
        "timeframe",
        "bar_ts",
        "status",
        "final_decision",
        "rule_confidence_score",
        "ml_confidence",
        "composite_score",
        "stop_loss",
        "take_profit",
        "error_code",
        "error_message",
        "top_features",  # optional; may be null
    ]:
        assert k in data, f"missing key: {k}"

    assert data["symbol"] == symbol
    assert data["timeframe"] == tf
    assert data["status"] == "COMPLETE"
    assert data["final_decision"] == "LONG"
    assert data["rule_confidence_score"] == 66
    assert data["ml_confidence"] == 72
    assert data["composite_score"] == 70


@pytest.mark.django_db
def test_history_returns_descending_and_limited():
    """
    Create 3 TradeAnalysis rows and request limit=2; expect two most recent by timestamp (desc).
    """
    MarketData = apps.get_model("backend", "MarketData")
    MarketDataFeatures = apps.get_model("backend", "MarketDataFeatures")
    TradeAnalysis = apps.get_model("backend", "TradeAnalysis")

    c = Client()

    symbol = f"GBPUSD_{uuid.uuid4().hex[:6]}"
    tf = "15m"
    base = timezone.now()

    md = MarketData.objects.create(
        symbol=symbol,
        timeframe=tf,
        timestamp=base,
        open=1.0,
        high=1.0,
        low=1.0,
        close=1.0,
        volume=0.0,
        provider="AllTick",
    )
    mdf, _ = MarketDataFeatures.objects.get_or_create(market_data=md)

    # Three analyses at ascending timestamps
    ts1 = base
    ts2 = base + timezone.timedelta(minutes=15)
    ts3 = base + timezone.timedelta(minutes=30)

    TradeAnalysis.objects.create(
        market_data_feature=mdf, timestamp=ts1, final_decision="NO_TRADE",
        rule_confidence_score=50, ml_confidence=50, composite_score=50,
        status="COMPLETE", started_at=ts1
    )
    TradeAnalysis.objects.create(
        market_data_feature=mdf, timestamp=ts2, final_decision="SHORT",
        rule_confidence_score=60, ml_confidence=65, composite_score=63,
        status="COMPLETE", started_at=ts2
    )
    TradeAnalysis.objects.create(
        market_data_feature=mdf, timestamp=ts3, final_decision="LONG",
        rule_confidence_score=70, ml_confidence=75, composite_score=73,
        status="COMPLETE", started_at=ts3
    )

    r = Client().get("/api/analysis/history", {"pair": symbol, "tf": tf, "limit": 2})
    assert r.status_code == 200, r.content

    arr = json.loads(r.content.decode("utf-8"))
    assert isinstance(arr, list)
    assert len(arr) == 2

    # Expect newest first (ts3, then ts2)
    first, second = arr[0], arr[1]
    assert first["final_decision"] == "LONG"
    assert second["final_decision"] == "SHORT"
