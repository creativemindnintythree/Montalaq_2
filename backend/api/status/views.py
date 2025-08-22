from typing import Optional
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.request import Request
from rest_framework import status

from backend.models import IngestionStatus


class IngestionStatusView(APIView):
    """
    GET /api/ingestion/status

    Returns:
    {
      "provider": "AllTick",
      "fallback_active": false,
      "key_age_days": 3,
      "pairs": [
        {
          "symbol": "EURUSD",
          "timeframe": "15m",
          "last_ts": "2025-08-21T18:52:00Z",
          "freshness": "GREEN",
          "data_freshness_sec": 58,
          "analyses_ok_5m": 12,
          "analyses_fail_5m": 0,
          "median_latency_ms": 135
        }
      ]
    }
    """

    def get_provider_block(self, rows) -> dict:
        # Choose provider metadata from the most recently updated row if available
        latest: Optional[IngestionStatus] = None
        if rows:
            latest = max(rows, key=lambda r: r.updated_at or timezone.make_aware(timezone.datetime.min))

        return {
            "provider": getattr(latest, "provider", None) if latest else None,
            "fallback_active": getattr(latest, "fallback_active", False) if latest else False,
            "key_age_days": getattr(latest, "key_age_days", None) if latest else None,
        }

    def get(self, request: Request):
        qs = IngestionStatus.objects.all().order_by("symbol", "timeframe")
        rows = list(qs)

        meta = self.get_provider_block(rows)

        pairs = []
        for r in rows:
            pairs.append(
                {
                    "symbol": r.symbol,
                    "timeframe": r.timeframe,
                    "last_ts": r.last_bar_ts,
                    "freshness": r.freshness_state,
                    "data_freshness_sec": r.data_freshness_sec,
                    "analyses_ok_5m": r.analyses_ok_5m,
                    "analyses_fail_5m": r.analyses_fail_5m,
                    "median_latency_ms": r.median_latency_ms,
                }
            )

        payload = {
            **meta,
            "pairs": pairs,
        }
        return Response(payload, status=status.HTTP_200_OK)
