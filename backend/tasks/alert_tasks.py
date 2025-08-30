from __future__ import annotations
import os
from celery import shared_task
from typing import Optional
from notify.dispatcher import send_alert
from django.apps import apps

def _PT():
    try:
        return apps.get_model('backend', 'ProviderTelemetry')
    except Exception:
        return None

def _UP():
    try:
        return apps.get_model('backend', 'UserPreference')
    except Exception:
        return None

def _quota_threshold() -> float:
    if _UP():
        obj = _UP().objects.filter(pk=1).first()
        if obj and obj.thresholds and isinstance(obj.thresholds, dict):
            v = obj.thresholds.get("quota_warn")
            if isinstance(v, (int,float)):
                return float(v)
    return float(os.getenv("ALERT_QUOTA_WARN_PCT", "80"))

@shared_task(name="backend.tasks.alert_tasks.check_provider_alerts")
def check_provider_alerts() -> dict:
    if not _PT():
        return {"ok": False, "reason": "no model"}
    thr = _quota_threshold()

    issues = []
    for row in _PT().objects.all():
        if row.quota_usage_pct is not None and row.quota_usage_pct >= thr:
            issues.append(("quota", row.provider, f"quota {row.quota_usage_pct:.1f}% ≥ {thr}%"))
        if bool(row.fallback_active):
            issues.append(("fallback", row.provider, "fallback_active=True"))
    for kind, provider, msg in issues:
        key = f"{kind}:{provider}"
        subject = f"[Montalaq] {provider} {kind} alert"
        body = f"{provider}: {msg}"
        send_alert(key, subject, body, tags=[kind, provider])
    return {"ok": True, "count": len(issues)}
