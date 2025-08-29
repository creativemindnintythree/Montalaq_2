from backend.api.status.augment import augment_status_payload
# backend/api/status/views.py

from typing import Dict, Optional

from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.request import Request
from rest_framework.response import Response

from backend.models import IngestionStatus
from .serializers import IngestionStatusSerializer


class IngestionStatusView(APIView):
    """
    GET /api/ingestion/status

    Returns an overview of ingestion freshness and heartbeat per (symbol, timeframe).
    The per‑pair objects include a derived `heartbeat` label from the serializer:
      - "Healthy"
      - "Connected – no new ticks"
      - "Provider stale"
      - "Unknown"
    """

    def _providers_summary(self, rows: list[IngestionStatus]) -> Dict[str, dict]:
        """
        Aggregate counts & last update per provider for a quick glance.
        """
        summary: Dict[str, dict] = {}
        grouped: Dict[str, list[IngestionStatus]] = {}
        for r in rows:
            grouped.setdefault(r.provider, []).append(r)

        for provider, items in grouped.items():
            last_updated = max(
                (i.updated_at for i in items if i.updated_at),
                default=None,
            )
            summary[provider] = {
                "pairs": len(items),
                "last_updated": last_updated,
            }
        return summary

    def _provider_meta(self, rows: list[IngestionStatus]) -> dict:
        """
        Surface latest provider meta (fallback/key_age_days) from the most recently updated row.
        """
        latest: Optional[IngestionStatus] = None
        if rows:
            latest = max(
                rows,
                key=lambda r: r.updated_at or timezone.make_aware(timezone.datetime.min),
            )

        return {
            "provider": getattr(latest, "provider", None) if latest else None,
            "fallback_active": getattr(latest, "fallback_active", False) if latest else False,
            "key_age_days": getattr(latest, "key_age_days", None) if latest else None,
        }

    def get(self, request: Request) -> Response:
        qs = IngestionStatus.objects.all().order_by("symbol", "timeframe")
        rows = list(qs)

        # Serialize pairs; serializer injects `heartbeat` and `expected_interval`
        data = IngestionStatusSerializer(rows, many=True).data

        payload = {
            "meta": self._provider_meta(rows),
            "pairs": data,  # each item includes: heartbeat, expected_interval, and core fields
            "providers_summary": self._providers_summary(rows),
        }
        return Response(augment_status_payload(payload))
