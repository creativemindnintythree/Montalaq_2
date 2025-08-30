from typing import Any, Dict
try:
    from backend.telemetry import get_provider_telemetry_map
except Exception:
    def get_provider_telemetry_map() -> Dict[str, dict]:
        return {}

def augment_status_payload(resp: Dict[str, Any]) -> Dict[str, Any]:
    """Merge telemetry into resp['providers_summary'] per provider key."""
    if not isinstance(resp, dict):
        return resp
    ps = resp.get("providers_summary") or {}
    telemetry = get_provider_telemetry_map()
    for prov, extra in telemetry.items():
        ps.setdefault(prov, {}).update(extra or {})
    resp["providers_summary"] = ps
    return resp
