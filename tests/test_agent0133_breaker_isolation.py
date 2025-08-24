# tests/test_agent0133_breaker_isolation.py
import uuid
import pytest
from django.apps import apps


@pytest.mark.django_db
def test_scheduler_skips_only_pairs_with_breaker_open(monkeypatch):
    """
    If one pair has breaker_open=True, scheduler.tick() must skip analysis only for that pair,
    while still scheduling analysis for other pairs/timeframes.
    """

    # Arrange models
    IngestionStatus = apps.get_model("backend", "IngestionStatus")

    # Two symbols on same timeframe
    broken = f"EURUSD_{uuid.uuid4().hex[:6]}"
    healthy = f"GBPUSD_{uuid.uuid4().hex[:6]}"
    tf = "1m"

    # Seed IngestionStatus rows to reflect current breaker/freshness state
    IngestionStatus.objects.create(
        symbol=broken,
        timeframe=tf,
        provider="AllTick",
        freshness_state="GREEN",
        escalation_level="ERROR",
        breaker_open=True,        # <- broken pair (should be skipped)
        fallback_active=False,
        key_age_days=0,
    )
    IngestionStatus.objects.create(
        symbol=healthy,
        timeframe=tf,
        provider="AllTick",
        freshness_state="GREEN",
        escalation_level="INFO",
        breaker_open=False,       # <- healthy pair (should be analyzed)
        fallback_active=False,
        key_age_days=0,
    )

    # Monkeypatch watchlist config so scheduler iterates exactly our pairs
    from backend.tasks import scheduler as sched_mod

    def fake_cfg():
        return {"pairs": [broken, healthy], "timeframes": [tf]}
    monkeypatch.setattr(sched_mod, "_cfg", fake_cfg)

    # Make freshness always GREEN/True to isolate breaker behavior
    def fake_is_fresh(sym, timeframe):
        return True, None, "GREEN"
    monkeypatch.setattr("backend.tasks.freshness.is_fresh", fake_is_fresh)

    # Track which analyses are enqueued
    calls = {"analyze": []}

    def fake_analyze_delay(sym, timeframe):
        calls["analyze"].append((sym, timeframe))

    # Stub out side effects we don't care about here
    monkeypatch.setattr("backend.tasks.analysis_tasks.analyze_latest.delay", fake_analyze_delay)
    monkeypatch.setattr("backend.tasks.ingest_tasks.ingest_once.delay", lambda: None)
    # If AMBER/RED, scheduler would call update_ingestion_status; ensure it isn't needed here
    monkeypatch.setattr("backend.tasks.freshness.update_ingestion_status", lambda s, t: None)

    # Act: run one scheduler tick synchronously
    sched_mod.tick()

    # Assert: only the healthy pair is scheduled
    assert (healthy, tf) in calls["analyze"], "Healthy pair should be analyzed"
    assert (broken, tf) not in calls["analyze"], "Broken pair must be skipped due to open breaker"
    # And exactly one analysis call happened
    assert len(calls["analyze"]) == 1
