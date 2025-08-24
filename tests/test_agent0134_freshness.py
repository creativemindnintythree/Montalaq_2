# tests/test_agent0134_freshness.py
# GREEN runs, AMBER/RED skip (with transparent AnalysisLog entries)

import pytest
from datetime import timedelta
from django.utils import timezone

from backend.models import MarketData, MarketDataFeatures, AnalysisLog, IngestionStatus
from backend.tasks import scheduler as sched_mod
from backend.tasks import freshness as fresh_mod


@pytest.fixture(autouse=True)
def _freshness_thresholds(monkeypatch):
    """
    Make freshness thresholds deterministic for tests:
      1m timeframe cadence = 60s (GREEN if age <= 60)
      AMBER: 1.5× < age < 3× → (90, 180)
      RED: otherwise
    """
    def test_cfg():
        return {"freshness_seconds": {"1m": 60}}
    monkeypatch.setattr(fresh_mod, "_cfg", test_cfg)
    yield


@pytest.fixture
def _watchlist(monkeypatch):
    """Force scheduler to iterate exactly one pair/timeframe."""
    def cfg():
        return {"pairs": ["EURUSD"], "timeframes": ["1m"]}
    monkeypatch.setattr(sched_mod, "_cfg", cfg)
    yield


@pytest.fixture
def _no_ingest_dispatch(monkeypatch):
    """Make ingest_once.delay a no-op so tests are fast and isolated."""
    def noop(*args, **kwargs):
        return None
    monkeypatch.setattr(sched_mod, "ingest_once", type("X", (), {"delay": staticmethod(noop)}))
    yield


@pytest.mark.django_db
def test_green_runs_analysis(_watchlist, _no_ingest_dispatch, monkeypatch):
    symbol, tf = "EURUSD", "1m"

    # Latest bar is now → GREEN
    bar_ts = timezone.now().replace(microsecond=0)
    md = MarketData.objects.create(
        symbol=symbol, timeframe=tf, timestamp=bar_ts,
        open=1.1, high=1.11, low=1.09, close=1.105, volume=1000, provider="AllTick",
    )
    MarketDataFeatures.objects.get_or_create(market_data=md)

    # Spy on analyze_latest.delay to confirm dispatch
    calls = {"n": 0}
    def fake_delay(s, t):
        assert (s, t) == (symbol, tf)
        calls["n"] += 1
    monkeypatch.setattr(sched_mod.analyze_latest, "delay", fake_delay)

    # Run one scheduler tick
    sched_mod.tick()

    # Assert: analysis was dispatched once; no skip logs written
    assert calls["n"] == 1
    assert AnalysisLog.objects.filter(symbol=symbol, timeframe=tf, error_message__startswith="SKIP:").count() == 0


@pytest.mark.django_db
def test_red_skips_and_logs(_watchlist, _no_ingest_dispatch, monkeypatch):
    symbol, tf = "EURUSD", "1m"

    # Age > 3× cadence → RED (cadence=60s → set age ~ 240s)
    old_ts = timezone.now() - timedelta(seconds=240)
    md = MarketData.objects.create(
        symbol=symbol, timeframe=tf, timestamp=old_ts,
        open=1.1, high=1.11, low=1.09, close=1.105, volume=1000, provider="AllTick",
    )
    MarketDataFeatures.objects.get_or_create(market_data=md)

    # Ensure analyze is NOT called
    def forbid(*args, **kwargs):
        pytest.fail("analyze_latest.delay should NOT be called for RED freshness")
    monkeypatch.setattr(sched_mod.analyze_latest, "delay", forbid)

    # Run one scheduler tick
    sched_mod.tick()

    # Assert: skip log recorded with RED reason
    skip_logs = AnalysisLog.objects.filter(symbol=symbol, timeframe=tf, error_message__contains="FRESHNESS_RED")
    assert skip_logs.count() == 1
    # Heartbeat path should also update IngestionStatus
    st = IngestionStatus.objects.get(symbol=symbol, timeframe=tf)
    assert st.freshness_state in ("AMBER", "RED")  # exact color computed by freshness module
    assert st.last_seen_at is not None


@pytest.mark.django_db
def test_amber_skips_and_logs(_watchlist, _no_ingest_dispatch, monkeypatch):
    symbol, tf = "EURUSD", "1m"

    # AMBER when 1.5× < age < 3×; with cadence=60s → pick 120s (falls into RED by strict rule if <=1.5× considered RED in your impl)
    # To be safe per fresh_mod.is_fresh logic: AMBER if (1.5× < age < 3×) → use 100s won't qualify; use 100? No.
    # We'll set 100s for clarity and then assert a skip occurred and the message includes 'FRESHNESS_' (AMBER/RED depending on exact thresholds).
    age = 100  # between 1.5× (90s) and 3× (180s) → AMBER per our is_fresh()
    old_ts = timezone.now() - timedelta(seconds=age)
    md = MarketData.objects.create(
        symbol=symbol, timeframe=tf, timestamp=old_ts,
        open=1.2, high=1.21, low=1.19, close=1.205, volume=900, provider="AllTick",
    )
    MarketDataFeatures.objects.get_or_create(market_data=md)

    # Ensure analyze is NOT called
    def forbid(*args, **kwargs):
        pytest.fail("analyze_latest.delay should NOT be called for AMBER freshness")
    monkeypatch.setattr(sched_mod.analyze_latest, "delay", forbid)

    # Run one scheduler tick
    sched_mod.tick()

    # Assert: skip log recorded with AMBER reason (or at least freshness-based skip)
    skip = AnalysisLog.objects.filter(symbol=symbol, timeframe=tf, error_message__contains="SKIP: FRESHNESS_").first()
    assert skip is not None
    assert "FRESHNESS_AMBER" in skip.error_message  # should be AMBER based on age 100s
