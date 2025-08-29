import json, os, smtplib, ssl
from email.message import EmailMessage
try:
    import requests
except Exception:
    requests = None

def send_webhook(payload: dict) -> bool:
    url = os.getenv("ALERT_WEBHOOK_URL")
    if not url or not requests:
        return False
    try:
        r = requests.post(url, json=payload, timeout=5)
        return 200 <= r.status_code < 300
    except Exception:
        return False

def send_email(subject: str, body: str) -> bool:
    host = os.getenv("SMTP_HOST"); port = int(os.getenv("SMTP_PORT","0") or 0)
    user = os.getenv("SMTP_USER"); pwd = os.getenv("SMTP_PASSWORD")
    from_addr = os.getenv("ALERT_EMAIL_FROM"); to_addr = os.getenv("ALERT_EMAIL_TO")
    if not (host and port and from_addr and to_addr):
        return False
    msg = EmailMessage()
    msg["Subject"] = subject; msg["From"] = from_addr; msg["To"] = to_addr
    msg.set_content(body)
    try:
        ctx = ssl.create_default_context()
        with smtplib.SMTP(host, port, timeout=5) as s:
            if os.getenv("SMTP_STARTTLS","1") in ("1","true","True"):
                s.starttls(context=ctx)
            if user and pwd:
                s.login(user, pwd)
            s.send_message(msg)
        return True
    except Exception:
        return False
