import pytest
from django.urls import reverse
from rest_framework.test import APIClient
from backend.models import IngestionStatus

@pytest.mark.django_db
def test_status_includes_provider_and_escalation_fields():
    client = APIClient()

    # Seed one IngestionStatus row
    st = IngestionStatus.objects.create(
        symbol="EURUSD",
        timeframe="1m",
        last_bar_ts="2025-08-23T00:00:00Z",
        last_ingest_ts="2025-08-23T00:00:30Z",
        freshness_state="GREEN",
        data_freshness_sec=30,
        provider="AllTick",
        key_age_days=1,
        fallback_active=False,
        analyses_ok_5m=10,
        analyses_fail_5m=1,
        median_latency_ms=123,
        escalation_level="WARN",
        breaker_open=False,
    )

    url = reverse("ingestion-status")  # from backend/api/status/urls.py
    response = client.get(url)
    assert response.status_code == 200

    payload = response.json()
    assert "pairs" in payload
    assert isinstance(payload["pairs"], list)
    assert len(payload["pairs"]) >= 1

    pair_entry = payload["pairs"][0]

    # Ensure provider, escalation_level, breaker_open exist
    assert "provider" in pair_entry
    assert pair_entry["provider"] == "AllTick"

    assert "escalation_level" in pair_entry
    assert pair_entry["escalation_level"] == "WARN"

    assert "breaker_open" in pair_entry
    assert pair_entry["breaker_open"] is False

    # Basic sanity check on freshness field
    assert pair_entry["freshness"] == "GREEN"
