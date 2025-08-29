from typing import Dict, Any
try:
    from .models import ProviderTelemetry
except Exception:
    ProviderTelemetry = None
def get_provider_telemetry_map() -> Dict[str, dict]:
    """Return {provider: {quota_usage_pct, key_age_days, fallback_active}}."""
    if not ProviderTelemetry:
        return {}
    out: Dict[str, dict] = {}
    for row in ProviderTelemetry.objects.all():
        out[row.provider] = {
            "quota_usage_pct": row.quota_usage_pct,
            "key_age_days": row.key_age_days,
            "fallback_active": bool(row.fallback_active),
        }
    return out
