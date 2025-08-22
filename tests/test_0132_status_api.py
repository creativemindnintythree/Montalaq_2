# tests/test_0132_status_api.py
import json
import math
import pytest
from django.utils import timezone
from django.urls import reverse
from rest_framework.test import APIClient

# We will exercise both:
#  1) The /api/ingestion/status response schema
#  2) The freshness coloring math using is_fresh()/update_ingestion_status()


@pytest.mark.django_db
def test_status_api_schema_returns_expected_shape():
    from backend.models import IngestionStatus

    # Seed a couple of rows
    now = timezone.now()
    row = IngestionStatus.objects.create(
        symbol="EURUSD",
        timeframe="15m",
        last_bar_ts=now,
        last_ingest_ts=now,
        freshness_state="GREEN",
        data_freshness_sec=58,
        provider="AllTick",
        key_age_days=3,
        fallback_active=False,
        analyses_ok_5m=12,
        analyses_fail_5m=0,
        median_latency_ms=135,
    )

    client = APIClient()
    resp = client.get("/api/ingestion/status")
    assert resp.status_code == 200

    body = resp.json()
    # Top-level keys
    assert "provider" in body
    assert "fallback_active" in body
    assert "key_age_days" in body
    assert "pairs" in body and isinstance(body["pairs"], list)

    # Provider block derived from most recent row
    assert body["provider"] == "AllTick"
    assert body["fallback_active"] is False
    assert body["key_age_days"] == 3

    # Item shape
    assert len(body["pairs"]) >= 1
    item = body["pairs"][0]
    for k in [
        "symbol",
        "timeframe",
        "last_ts",
        "freshness",
        "data_freshness_sec",
        "analyses_ok_5m",
        "analyses_fail_5m",
        "median_latency_ms",
    ]:
        assert k in item

    assert item["symbol"] == "EURUSD"
    assert item["timeframe"] == "15m"
    assert item["freshness"] == "GREEN"
    assert item["analyses_ok_5m"] == 12
    assert item["analyses_fail_5m"] == 0
    assert item["median_latency_ms"] == 135


@pytest.mark.django_db
def test_freshness_coloring_math_1x_1p5x_3x(monkeypatch):
    """
    Validate freshness logic boundaries per 013.2 brief:
      - GREEN: age <= 1× cadence
      - AMBER: 1.5× < age < 3× cadence
      - RED:   age >= 3× cadence
    Note: We drive this via MarketData timestamps + update_ingestion_status().
    """

    # Arrange thresholds via monkeypatch of _cfg() to avoid relying on real file.
    from backend.tasks import freshness as fr

    def fake_cfg():
        return {
            "freshness_seconds": {
                "1m": 60,
                "15m": 900,
            },
            "pairs": ["EURUSD"],
            "timeframes": ["1m"],
        }

    monkeypatch.setattr(fr, "_cfg", fake_cfg)

    # Create MarketData samples at different ages
    from django.apps import apps
    MarketData = apps.get_model("backend", "MarketData")
    IngestionStatus = apps.get_model("backend", "IngestionStatus")

    symbol = "EURUSD"
    tf = "1m"
    cadence = 60  # seconds

    now = timezone.now()

    # Helper to insert a bar with a given "age" (seconds) and then update status
    def insert_and_update(age_sec):
        ts = now - timezone.timedelta(seconds=age_sec)
        MarketData.objects.create(
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
        # compute/update
        fr.update_ingestion_status(symbol, tf)
        return IngestionStatus.objects.get(symbol=symbol, timeframe=tf)

    # Case A: age <= 1× (GREEN)
    st_green = insert_and_update(age_sec=int(0.9 * cadence))
    assert st_green.freshness_state == "GREEN"

    # Case B: 1.5× < age < 3× (AMBER) e.g., 2×
    st_amber = insert_and_update(age_sec=int(2.0 * cadence))
    # Expect AMBER per spec
    assert st_amber.freshness_state == "AMBER", (
        f"Expected AMBER for age ~2x cadence, got {st_amber.freshness_state}"
    )

    # Case C: age >= 3× (RED) e.g., 3.1×
    st_red = insert_and_update(age_sec=int(3.1 * cadence))
    assert st_red.freshness_state == "RED"
