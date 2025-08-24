# backend/api/status/serializers.py
from __future__ import annotations

from typing import Any

from django.utils import timezone
from rest_framework import serializers

from backend.models import IngestionStatus
# IMPORTANT: import the module, not the symbol, so tests can monkeypatch _cfg
from backend.tasks import freshness as fresh_mod


class IngestionStatusSerializer(serializers.ModelSerializer):
    # Human-friendly status derived from heartbeat + freshness color
    heartbeat = serializers.SerializerMethodField()
    # Expose the expected interval (in seconds) so the UI can show context/tooltips
    expected_interval = serializers.SerializerMethodField()

    class Meta:
        model = IngestionStatus
        fields = (
            # identity
            "symbol",
            "timeframe",
            # bar / ingest timestamps
            "last_bar_ts",
            "last_ingest_ts",
            # freshness
            "freshness_state",
            "data_freshness_sec",
            # provider + ops
            "provider",
            "key_age_days",
            "fallback_active",
            # KPIs
            "analyses_ok_5m",
            "analyses_fail_5m",
            "median_latency_ms",
            # control plane
            "escalation_level",
            "breaker_open",
            # heartbeat & derived label
            "last_seen_at",
            "expected_interval",
            "heartbeat",
        )

    # ---- derived fields ----

    def get_expected_interval(self, obj: IngestionStatus) -> int | None:
        """
        Return the expected interval (seconds) for this timeframe, as used by freshness gating.
        Falls back to None if timeframe is unknown in config.
        """
        try:
            cfg = fresh_mod._cfg()
            return int(cfg["freshness_seconds"][obj.timeframe])
        except Exception:
            return None

    def get_heartbeat(self, obj: IngestionStatus) -> str:
        """
        Render a human-friendly heartbeat label:
          - "Healthy" when GREEN and heartbeat is within expected interval
          - "Connected – no new ticks" when GREEN but heartbeat age > expected interval
          - "Provider stale" when AMBER/RED (regardless of heartbeat age)
          - "Unknown" if last_seen_at is missing
        """
        if not obj.last_seen_at:
            return "Unknown"

        expected = self.get_expected_interval(obj)
        age_sec = (timezone.now() - obj.last_seen_at).total_seconds()

        # If provider freshness says we're behind, surface that first.
        if obj.freshness_state in ("AMBER", "RED"):
            return "Provider stale"

        # Otherwise we're GREEN; distinguish quiet vs healthy by heartbeat age.
        if expected is not None and age_sec > expected:
            return "Connected – no new ticks"

        return "Healthy"
