# tests/test_agent0134_heartbeat.py
# Quiet vs Broken feed distinction:
# - "Healthy"                    → GREEN + heartbeat age <= expected interval
# - "Connected – no new ticks"   → GREEN + heartbeat age > expected interval
# - "Provider stale"             → AMBER/RED regardless of heartbeat age
# - "Unknown"                    → last_seen_at is None

import pytest
from datetime import timedelta

from django.utils import timezone
from rest_framework.test import APIRequestFactory

from backend.models import IngestionStatus
from backend.api.status.serializers import IngestionStatusSerializer
from backend.api.status.views import IngestionStatusView
from backend.tasks import freshness as fresh_mod


@pytest.fixture(autouse=True)
def _fixed_cfg(monkeypatch):
    """
    Make expected interval deterministic:
      timeframe '1m' => 60 seconds (GREEN if heartbeat age <= 60)
    """
    def test_cfg():
        return {"freshness_seconds": {"1m": 60}}
    monkeypatch.setattr(fresh_mod, "_cfg", test_cfg)
    yield


@pytest.mark.django_db
def test_heartbeat_healthy():
    now = timezone.now()
    obj = IngestionStatus.objects.create(
        symbol="EURUSD",
        timeframe="1m",
        freshness_state="GREEN",
        last_seen_at=now - timedelta(seconds=10),  # within 60s
        last_bar_ts=now - timedelta(seconds=30),
        provider="AllTick",
    )
    data = IngestionStatusSerializer(obj).data
    assert data["expected_interval"] == 60
    assert data["heartbeat"] == "Healthy"


@pytest.mark.django_db
def test_heartbeat_connected_no_new_ticks():
    now = timezone.now()
    obj = IngestionStatus.objects.create(
        symbol="EURUSD",
        timeframe="1m",
        freshness_state="GREEN",
        last_seen_at=now - timedelta(seconds=120),  # beyond 60s
        last_bar_ts=now - timedelta(seconds=180),
        provider="AllTick",
    )
    data = IngestionStatusSerializer(obj).data
    assert data["expected_interval"] == 60
    assert data["heartbeat"] == "Connected – no new ticks"


@pytest.mark.django_db
def test_heartbeat_provider_stale_amber_overrides_age():
    now = timezone.now()
    # Even with a recent heartbeat, AMBER must show "Provider stale"
    obj = IngestionStatus.objects.create(
        symbol="EURUSD",
        timeframe="1m",
        freshness_state="AMBER",
        last_seen_at=now - timedelta(seconds=5),
        last_bar_ts=now - timedelta(seconds=200),  # old bar caused AMBER
        provider="AllTick",
    )
    data = IngestionStatusSerializer(obj).data
    assert data["heartbeat"] == "Provider stale"


@pytest.mark.django_db
def test_heartbeat_provider_stale_red_overrides_age():
    now = timezone.now()
    obj = IngestionStatus.objects.create(
        symbol="EURUSD",
        timeframe="1m",
        freshness_state="RED",
        last_seen_at=now - timedelta(seconds=5),
        last_bar_ts=now - timedelta(minutes=10),
        provider="AllTick",
    )
    data = IngestionStatusSerializer(obj).data
    assert data["heartbeat"] == "Provider stale"


@pytest.mark.django_db
def test_heartbeat_unknown_when_missing_last_seen():
    now = timezone.now()
    obj = IngestionStatus.objects.create(
        symbol="EURUSD",
        timeframe="1m",
        freshness_state="GREEN",
        last_seen_at=None,  # missing heartbeat
        last_bar_ts=now - timedelta(seconds=20),
        provider="AllTick",
    )
    data = IngestionStatusSerializer(obj).data
    assert data["heartbeat"] == "Unknown"


@pytest.mark.django_db
def test_api_view_surfaces_heartbeat_field():
    """
    Smoke test the API view: ensures 'heartbeat' & 'expected_interval' appear in payload
    and reflect serializer logic.
    """
    now = timezone.now()
    IngestionStatus.objects.create(
        symbol="EURUSD",
        timeframe="1m",
        freshness_state="GREEN",
        last_seen_at=now - timedelta(seconds=120),  # will produce "Connected – no new ticks"
        last_bar_ts=now - timedelta(seconds=180),
        provider="AllTick",
    )

    factory = APIRequestFactory()
    request = factory.get("/api/ingestion/status")
    response = IngestionStatusView.as_view()(request)

    assert response.status_code == 200
    body = response.data
    assert "pairs" in body and isinstance(body["pairs"], list) and len(body["pairs"]) == 1
    item = body["pairs"][0]
    assert item["expected_interval"] == 60
    assert item["heartbeat"] == "Connected – no new ticks"
