# tests/test_agent0133_notifications.py
import uuid
import pytest
from django.apps import apps
from django.utils import timezone
from django.conf import settings


@pytest.mark.django_db
def test_signal_notification_dedupes_per_bar(monkeypatch):
    """
    Should send exactly one notification for a given (symbol, timeframe, bar_ts)
    even if the hook is invoked multiple times. Dedupe is enforced by:
      - IngestionStatus.last_signal_bar_ts (DB)
      - notify task's own cache-based dedupe
    """
    MarketData = apps.get_model("backend", "MarketData")
    MarketDataFeatures = apps.get_model("backend", "MarketDataFeatures")
    TradeAnalysis = apps.get_model("backend", "TradeAnalysis")
    IngestionStatus = apps.get_model("backend", "IngestionStatus")

    # Ensure threshold will pass
    settings.NOTIFICATION_DEFAULTS["composite_notify_threshold"] = 70

    symbol = f"EURUSD_{uuid.uuid4().hex[:6]}"
    tf = "1m"
    ts = timezone.now()

    md = MarketData.objects.create(
        symbol=symbol,
        timeframe=tf,
        timestamp=ts,
        open=1.0, high=1.0, low=1.0, close=1.0,
        volume=0.0,
        provider="AllTick",
    )
    mdf, _ = MarketDataFeatures.objects.get_or_create(market_data=md)

    ta = TradeAnalysis.objects.create(
        market_data_feature=mdf,
        timestamp=ts,
        final_decision="LONG",
        rule_confidence_score=60,
        ml_confidence=90,
        composite_score=80,  # >= 70 threshold
        stop_loss=0.95,
        take_profit=1.05,
        status="COMPLETE",
        started_at=ts,
    )

    calls = {"n": 0, "last_payload": None}

    def fake_delay(**kwargs):
        calls["n"] += 1
        calls["last_payload"] = kwargs

    # Patch send_notification.delay
    monkeypatch.setattr("backend.tasks.notify.send_notification.delay", fake_delay)

    # Import after patch so the hook uses the patched function
    from backend.tasks.analysis_hooks import maybe_notify_signal

    # First invocation should send
    out1 = maybe_notify_signal(ta)
    assert out1 is True
    assert calls["n"] == 1

    # Second invocation (same bar) should dedupe
    out2 = maybe_notify_signal(ta)
    assert out2 is False
    assert calls["n"] == 1  # unchanged

    # DB dedupe persisted
    st = IngestionStatus.objects.get(symbol=symbol, timeframe=tf)
    assert st.last_signal_bar_ts == ts


@pytest.mark.django_db
def test_signal_notification_respects_threshold(monkeypatch):
    """
    If composite_score is below threshold, no notification should be sent.
    """
    MarketData = apps.get_model("backend", "MarketData")
    MarketDataFeatures = apps.get_model("backend", "MarketDataFeatures")
    TradeAnalysis = apps.get_model("backend", "TradeAnalysis")

    # Raise threshold above the composite we'll set
    settings.NOTIFICATION_DEFAULTS["composite_notify_threshold"] = 90

    symbol = f"GBPUSD_{uuid.uuid4().hex[:6]}"
    tf = "15m"
    ts = timezone.now()

    md = MarketData.objects.create(
        symbol=symbol,
        timeframe=tf,
        timestamp=ts,
        open=1.0, high=1.0, low=1.0, close=1.0,
        volume=0.0,
        provider="AllTick",
    )
    mdf, _ = MarketDataFeatures.objects.get_or_create(market_data=md)

    ta = TradeAnalysis.objects.create(
        market_data_feature=mdf,
        timestamp=ts,
        final_decision="SHORT",
        rule_confidence_score=40,
        ml_confidence=45,
        composite_score=70,  # below threshold=90
        status="COMPLETE",
        started_at=ts,
    )

    calls = {"n": 0}

    def fake_delay(**kwargs):
        calls["n"] += 1

    monkeypatch.setattr("backend.tasks.notify.send_notification.delay", fake_delay)

    from backend.tasks.analysis_hooks import maybe_notify_signal

    out = maybe_notify_signal(ta)
    # Conditions not met -> no send
    assert out is False
    assert calls["n"] == 0


@pytest.mark.django_db
def test_signal_notification_sends_again_on_new_bar(monkeypatch):
    """
    Dedupe window is per bar_ts. A subsequent bar should notify again.
    """
    MarketData = apps.get_model("backend", "MarketData")
    MarketDataFeatures = apps.get_model("backend", "MarketDataFeatures")
    TradeAnalysis = apps.get_model("backend", "TradeAnalysis")

    settings.NOTIFICATION_DEFAULTS["composite_notify_threshold"] = 70

    symbol = f"XAUUSD_{uuid.uuid4().hex[:6]}"
    tf = "1m"
    base = timezone.now()

    # bar 1
    md1 = MarketData.objects.create(
        symbol=symbol, timeframe=tf, timestamp=base,
        open=1.0, high=1.0, low=1.0, close=1.0, volume=0.0, provider="AllTick"
    )
    mdf1, _ = MarketDataFeatures.objects.get_or_create(market_data=md1)
    ta1 = TradeAnalysis.objects.create(
        market_data_feature=mdf1, timestamp=base, final_decision="LONG",
        rule_confidence_score=60, ml_confidence=90, composite_score=80,
        status="COMPLETE", started_at=base
    )

    # bar 2 (later)
    bar2 = base + timezone.timedelta(minutes=1)
    md2 = MarketData.objects.create(
        symbol=symbol, timeframe=tf, timestamp=bar2,
        open=1.0, high=1.0, low=1.0, close=1.0, volume=0.0, provider="AllTick"
    )
    mdf2, _ = MarketDataFeatures.objects.get_or_create(market_data=md2)
    ta2 = TradeAnalysis.objects.create(
        market_data_feature=mdf2, timestamp=bar2, final_decision="LONG",
        rule_confidence_score=61, ml_confidence=92, composite_score=82,
        status="COMPLETE", started_at=bar2
    )

    count = {"n": 0}

    def fake_delay(**kwargs):
        count["n"] += 1

    monkeypatch.setattr("backend.tasks.notify.send_notification.delay", fake_delay)
    from backend.tasks.analysis_hooks import maybe_notify_signal

    # First bar -> notify
    assert maybe_notify_signal(ta1) is True
    # Same bar again -> dedupe
    assert maybe_notify_signal(ta1) is False

    # Next bar -> notify again
    assert maybe_notify_signal(ta2) is True

    assert count["n"] == 2  # one per distinct bar
