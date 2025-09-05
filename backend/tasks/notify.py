# backend/tasks/notify.py
"""
013.3 Notifications task

- Consumes centralized error taxonomy from backend/errors.py (013.2.1).
- Multi-channel delivery: email, generic webhook, Slack (via webhook).
- Retry/backoff via Celery; safe "dry run" and light per-minute rate limiting.
- Optional dedupe for signal events (per pair/tf/bar_ts) to avoid double sends.

Environment / settings integration:
  settings.NOTIFICATION_DEFAULTS = {
      "composite_notify_threshold": int,
      "dedupe_window_sec": int,
      "channels": {
          "email":   {"enabled": bool, "from_addr": str, "to_addrs": list[str]},
          "webhook": {"enabled": bool, "url": str},
          "slack":   {"enabled": bool, "webhook_url": str},
      },
      "dry_run": bool,
      "max_events_per_minute": int,
  }
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional
import requests
from celery import shared_task
from celery.utils.log import get_task_logger

logger = get_task_logger(__name__)
from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone
from django.core.cache import cache

# 013.2.1 centralized taxonomy
from backend.errors import ErrorCode, map_exception  # noqa: F401 (map_exception available to callers)

# ----- severity helpers ------------------------------------------------------

_SEV_ORDER = {"DEBUG":0,"INFO":1,"WARNING":2,"ERROR":3,"CRITICAL":4}
_SEV_ALIAS = {"WARN":"WARNING"}

def _normalize_severity(s):
    s = (s or "INFO").upper()
    return _SEV_ALIAS.get(s, s) if s in _SEV_ORDER or s in _SEV_ALIAS else "INFO"


def _meets_min_severity(level: str, min_required: str) -> bool:
    """Return True if level >= min_required (using INFO < WARN < ERROR < CRITICAL)."""
    return _SEV_ORDER.get(level, 0) >= _SEV_ORDER.get(min_required, 0)


# ----- rate limiting & dedupe ------------------------------------------------

def _rate_key(event: str, severity: str) -> str:
    now_min = timezone.now().strftime("%Y%m%d%H%M")
    return f"notify:rate:{event}:{severity}:{now_min}"


def _rate_ok(event: str, severity: str, per_minute_limit: int) -> bool:
    k = _rate_key(event, severity)
    current = cache.get(k, 0)
    if current >= per_minute_limit:
        return False
    cache.set(k, current + 1, timeout=70)  # ~1 minute window
    return True


def _dedupe_key(payload: Dict[str, Any]) -> Optional[str]:
    """
    Build a dedupe cache key for signal-like events.

    We use (symbol, timeframe, bar_ts) if present; otherwise None (no dedupe).
    """
    sym = payload.get("symbol")
    tf = payload.get("timeframe")
    bar_ts = payload.get("bar_ts")
    if sym and tf and bar_ts:
        return f"notify:dedupe:signal:{sym}:{tf}:{bar_ts}"
    return None


def _dedupe_ok(payload: Dict[str, Any], window_sec: int) -> bool:
    k = _dedupe_key(payload)
    if not k:
        return True
    if cache.get(k):
        return False
    cache.set(k, 1, timeout=window_sec)
    return True


# ----- core senders ----------------------------------------------------------

def _send_email(subject: str, body: str) -> None:
    cfg = settings.NOTIFICATION_DEFAULTS["channels"]["email"]
    to_addrs = [a for a in cfg.get("to_addrs", []) if a]
    try:
        sent = send_mail(
            subject=subject,
            message=body,
            from_email=cfg["from_addr"],
            recipient_list=to_addrs,
            fail_silently=False,
        )
        logger.info("notify.sent: email to=%s count=%s", ",".join(to_addrs), sent)
    except Exception as e:
        logger.exception("notify.error: email to=%s err=%s", ",".join(to_addrs), e)
        raise


def _send_webhook(url: str, payload: Dict[str, Any]) -> None:
    try:
        resp = requests.post(url, json=payload, timeout=10)
        logger.info("notify.sent: webhook status=%s url=%s", getattr(resp, "status_code", "?"), url)
        # Treat non-2xx as failures to enable retries:
        resp.raise_for_status()
    except Exception as e:
        logger.exception("notify.error: webhook url=%s err=%s", url, e)
        raise


def _send_slack(webhook_url: str, text: str, payload: Dict[str, Any]) -> None:
    # Simple Slack-compatible webhook (blocks/attachments optional)
    msg = {
        "text": text,
        "blocks": [
            {"type": "section", "text": {"type": "mrkdwn", "text": text}},
            {"type": "section", "text": {"type": "mrkdwn", "text": f"```{json.dumps(payload, default=str)}```"}},
        ],
    }
    try:
        resp = requests.post(webhook_url, json=msg, timeout=10)
        logger.info("notify.sent: slack status=%s url=%s", getattr(resp, "status_code", "?"), webhook_url)
        resp.raise_for_status()
    except Exception as e:
        logger.exception("notify.error: slack url=%s err=%s", webhook_url, e)
        raise


# ----- public Celery task ----------------------------------------------------

@shared_task(
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=5,
)
def send_notification(event: str, severity: str, payload: Dict[str, Any]) -> None:
    # Normalize severity
    severity = (severity or "INFO").upper()
    if severity == "WARN":
        severity = "WARNING"

    cfg = settings.NOTIFICATION_DEFAULTS
    channels = cfg.get("channels", {})
    dry_run = bool(cfg.get("dry_run", False))
    per_min_limit = int(cfg.get("max_events_per_minute", 60))
    dedupe_window_sec = int(cfg.get("dedupe_window_sec", 900))

# severity floor (per-event: only enabled channels listening to this event)
try:
    from backend.models import NotificationChannel as _C
    LEVELS = ["DEBUG","INFO","WARNING","ERROR","CRITICAL"]
    def _idx(x):
        try:
            return LEVELS.index(str(x or "INFO").upper())
        except ValueError:
            return LEVELS.index("INFO")

    qs = _C.objects.filter(enabled=True)
    candidates = []
    for _c in qs:
        evs = getattr(_c, "events", None)
        if isinstance(evs, dict):
            listens = bool(evs.get(event, False))   # strict: only explicit True
        else:
            listens = False                         # no map -> not listening
        if listens:
            candidates.append(_c)

    if not candidates:
        logger.info("notify.skip: no-channel-listening event=%s severity=%s", event, severity)
        return

    floors = [_idx(_c.min_severity) for _c in candidates]
    floor_idx = min(floors)
    sev_idx = _idx(severity)
    if sev_idx < floor_idx:
        logger.info(
            "notify.skip: below-floor (per-event) event=%s severity=%s floor_idx=%s",
            event, severity, floor_idx
        )
        return
except Exception:
    pass


    # rate limit (coarse, per event+severity)
    rkey = _rate_key(event, severity)
    if not _rate_ok(event, severity, per_minute_limit=per_min_limit):
        logger.info("notify.skip: rate-limited key=%s", rkey)
        return

    # dedupe: only for signal-like notifications where bar context is present
    if event == "signal" and not _dedupe_ok(payload, dedupe_window_sec):
        dkey = _dedupe_key(payload)
        logger.info("notify.skip: deduped key=%s payload_keys=%s", dkey, sorted(list(payload.keys())))
        return


    title = payload.get("title") or f"{event} event"
    err_code = payload.get("error_code")  # should be ErrorCode (Enum) or str
    if isinstance(err_code, ErrorCode):
        err_code = err_code.value
    subject = f"[{severity}] {title}"
    text_line = f"*{severity}* {title}"
    if err_code:
        subject += f" ({err_code})"
        text_line += f" ({err_code})"

    # If dry-run, skip actual sends (useful in tests / staging)
    if dry_run:
        return

    # EMAIL
    email_cfg = channels.get("email") or {}
    if email_cfg.get("enabled") and _meets_min_severity(severity, "INFO"):
        _send_email(subject, json.dumps(payload, default=str))

    # GENERIC WEBHOOK
    webhook_cfg = channels.get("webhook") or {}
    if webhook_cfg.get("enabled") and webhook_cfg.get("url") and _meets_min_severity(severity, "INFO"):
        _send_webhook(
            webhook_cfg["url"],
            {"event": event, "severity": severity, "payload": payload},
        )

    # SLACK (webhook)
    slack_cfg = channels.get("slack") or {}
    if slack_cfg.get("enabled") and slack_cfg.get("webhook_url") and _meets_min_severity(severity, "INFO"):
        _send_slack(slack_cfg["webhook_url"], text_line, payload)
