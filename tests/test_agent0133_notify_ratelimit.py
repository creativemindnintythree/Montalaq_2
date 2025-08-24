# tests/test_agent0133_notify_ratelimit.py
import types
import pytest
from django.conf import settings


@pytest.mark.django_db
def test_notify_rate_limit_caps_deliveries(monkeypatch):
    """
    Ensure NOTIFICATION_DEFAULTS['max_events_per_minute'] is respected.
    We enable only the webhook channel and monkeypatch requests.post
    to count actual outbound attempts.

    Expectation: with max_events_per_minute=3 and 6 send attempts in the
    same minute bucket, only 3 deliveries are attempted.
    """
    # --- Configure notifications (webhook only) ---
    settings.NOTIFICATION_DEFAULTS["channels"]["email"]["enabled"] = False
    settings.NOTIFICATION_DEFAULTS["channels"]["slack"]["enabled"] = False
    settings.NOTIFICATION_DEFAULTS["channels"]["webhook"]["enabled"] = True
    settings.NOTIFICATION_DEFAULTS["channels"]["webhook"]["url"] = "http://example.test/hook"

    # Force live sends (no dry run) so channel delivery path executes
    settings.NOTIFICATION_DEFAULTS["dry_run"] = False

    # Tight rate limit for the test
    settings.NOTIFICATION_DEFAULTS["max_events_per_minute"] = 3

    # --- Patch outbound HTTP used by webhook channel ---
    from backend.tasks import notify as notify_mod

    calls = {"post": 0}

    class _DummyResp:
        status_code = 200
        def json(self): return {}

    def fake_post(url, json=None, headers=None, timeout=None):
        calls["post"] += 1
        return _DummyResp()

    # Some implementations import requests at module level; patch there.
    if hasattr(notify_mod, "requests"):
        monkeypatch.setattr(notify_mod.requests, "post", fake_post, raising=True)
    else:
        # Fallback (shouldn't happen if requests is imported in notify.py)
        import requests  # noqa: F401
        monkeypatch.setattr("requests.post", fake_post, raising=True)

    # --- Execute multiple sends within the same minute window ---
    send_fn = getattr(notify_mod.send_notification, "run", None)
    if isinstance(send_fn, types.FunctionType):
        # Celery shared_task with .run available: call synchronously
        for i in range(6):
            notify_mod.send_notification.run(
                event="signal",
                severity="INFO",
                payload={"title": f"rate-limit-test {i}"},
            )
    else:
        # If not a Celery task, call the function directly
        for i in range(6):
            notify_mod.send_notification(
                event="signal",
                severity="INFO",
                payload={"title": f"rate-limit-test {i}"},
            )

    # --- Assert: only max_events_per_minute deliveries attempted ---
    assert calls["post"] == 3, f"expected 3 webhook posts, got {calls['post']}"
