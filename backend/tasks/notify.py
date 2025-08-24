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
from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone
from django.core.cache import cache

# 013.2.1 centralized taxonomy
from backend.errors import ErrorCode, map_exception  # noqa: F401 (map_exception available to callers)

# ----- severity helpers ------------------------------------------------------

_SEV_ORDER = {"INFO": 0, "WARN": 1, "ERROR": 2, "CRITICAL": 3}


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
    send_mail(
        subject=subject,
        message=body,
        from_email=cfg["from_addr"],
        recipient_list=[a for a in cfg.get("to_addrs", []) if a],
        fail_silently=False,
    )


def _send_webhook(url: str, payload: Dict[str, Any]) -> None:
    requests.post(url, json=payload, timeout=10)


def _send_slack(webhook_url: str, text: str, payload: Dict[str, Any]) -> None:
    # Simple Slack-compatible webhook (blocks/attachments optional)
    msg = {
        "text": text,
        "blocks": [
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": text},
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"```{json.dumps(payload, default=str)}```"},
            },
        ],
    }
    requests.post(webhook_url, json=msg, timeout=10)


# ----- public Celery task ----------------------------------------------------

@shared_task(
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=5,
)
def send_notification(event: str, severity: str, payload: Dict[str, Any]) -> None:
    """
    Send a notification.

    Args:
        event: "signal" | "failure" | "freshness" | "recovery" | custom
        severity: "INFO" | "WARN" | "ERROR" | "CRITICAL"
        payload: dict with context. May include:
            - title (str)
            - symbol (str), timeframe (str), bar_ts (iso-like str)
            - decision (str), composite (int), sl (str/num), tp (str/num)
            - error_code (ErrorCode | str), error_message (str)
            - any additional fields safe to serialize
    """
    cfg = settings.NOTIFICATION_DEFAULTS
    channels = cfg.get("channels", {})
    dry_run = bool(cfg.get("dry_run", False))
    per_min_limit = int(cfg.get("max_events_per_minute", 60))
    dedupe_window_sec = int(cfg.get("dedupe_window_sec", 900))

    # rate limit (coarse, per event+severity)
    if not _rate_ok(event, severity, per_minute_limit=per_min_limit):
        return

    # dedupe: only for signal-like notifications where bar context is present
    if event == "signal" and not _dedupe_ok(payload, dedupe_window_sec):
        return

    # Build common subject/text
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
