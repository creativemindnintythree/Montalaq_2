from .channels import send_webhook, send_email
import os, time
from typing import Dict, List
_COOLDOWN = int(os.getenv("ALERT_COOLDOWN_SEC", "600"))
_last_sent: Dict[str, float] = {}

def _should_send(key: str, now: float) -> bool:
    ts = _last_sent.get(key, 0.0)
    if now - ts >= _COOLDOWN:
        _last_sent[key] = now
        return True
    return False

def send_alert(key: str, subject: str, body: str, tags: List[str] | None = None):
    now = time.monotonic()
    if not _should_send(key, now):
        return
    payload = {"subject": subject, "body": body, "tags": tags or []}
    ok_webhook = send_webhook(payload)
    ok_email = send_email(subject, body)
    print(f"ALERT key={key} webhook={ok_webhook} email={ok_email} :: {subject}")
