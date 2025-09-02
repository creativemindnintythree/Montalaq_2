from django.apps import apps
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import IngestionStatusSerializer


def ingestion_status(request):
    IngestionStatus = apps.get_model("backend", "IngestionStatus")
    # IMPORTANT: use updated_at (not last_updated)
    rows = list(IngestionStatus.objects.all().order_by("-updated_at"))

    # Build per-provider summary
    providers_summary = {}
    for r in rows:
        d = providers_summary.setdefault(r.provider, {"pairs": 0, "updated_at": None})
        d["pairs"] += 1
        if r.updated_at and (d["updated_at"] is None or r.updated_at > d["updated_at"]):
            d["updated_at"] = r.updated_at

    latest = rows[0] if rows else None

    # Serialize pairs via DRF serializer
    pairs = IngestionStatusSerializer(rows, many=True).data

    # Back-compat aliases the tests expect
    for item in pairs:
        # tests read 'freshness' as an alias for freshness_state
        item.setdefault("freshness", item.get("freshness_state"))
        # tests read 'last_ts' (prefer last_ingest_ts, fallback to last_bar_ts)
        item.setdefault("last_ts", item.get("last_ingest_ts") or item.get("last_bar_ts"))

    payload = {
        "provider": latest.provider if latest else None,
        "fallback_active": bool(getattr(latest, "fallback_active", False)) if latest else False,
        # tests expect key_age_days at top-level (from the most recent row)
        "key_age_days": getattr(latest, "key_age_days", None) if latest else None,
        "providers_summary": providers_summary,
        "pairs": pairs,
    }
    return Response(payload)


class IngestionStatusView(APIView):
    """Compatibility wrapper for tests that call the CBV."""
    def get(self, request, *args, **kwargs):
        return ingestion_status(request)
