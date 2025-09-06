from django.test import TestCase, override_settings
from unittest.mock import patch, Mock
from django.utils import timezone
from django.core.cache import cache

# Celery task entrypoint
from backend.tasks.notify import send_notification
# DB-backed channel model (your guard checks DB, not just settings)
from backend.models import NotificationChannel


def iso_now():
    # RFC3339-ish without micros, with trailing Z to match your payloads
    return timezone.now().strftime("%Y-%m-%dT%H:%M:%SZ")


# Base NOTIFICATION_DEFAULTS for tests; channels in DB control listening.
BASE = {
    "dry_run": True,   # side-effect free by default; override per-test when needed
    "max_events_per_minute": 60,
    "dedupe_window_sec": 900,
    "channels": {
        "webhook": {"enabled": True, "url": "https://httpbin.org/post", "secret": ""},
        "email":   {"enabled": False, "from_addr": "noreply@example.com", "to_addrs": []},
        "slack":   {"enabled": False, "webhook_url": ""},
    },
}


@override_settings(NOTIFICATION_DEFAULTS=BASE)
class TestNotifyGuards(TestCase):
    def setUp(self):
        cache.clear()
        NotificationChannel.objects.all().delete()

        # Create a listening channel in the test DB so the guard passes.
        NotificationChannel.objects.create(
            name="t-webhook",
            channel_type="WEBHOOK",
            enabled=True,
            min_severity="INFO",                 # floor allows INFO
            events={"signal": True},             # listens to "signal"
            config={"url": "https://httpbin.org/post"},
            dedupe_window_sec=900,
        )

    def _payload(self, title="t"):
        return {"symbol": "X", "timeframe": "1m", "bar_ts": iso_now(), "title": title}

    @patch("backend.tasks.notify.requests.post")
    def test_webhook_dry_run_short_circuits(self, mpost: Mock):
        # With dry_run=True and a listening channel, network should still be skipped.
        send_notification.run("signal", "INFO", self._payload("dry-run"))
        mpost.assert_not_called()

    @override_settings(NOTIFICATION_DEFAULTS={**BASE, "dry_run": False})
    @patch("backend.tasks.notify.requests.post")
    def test_webhook_500_triggers_autoretry(self, mpost: Mock):
        # _send_webhook logs and re-raises so Celery autoretry can kick in.
        mpost.return_value = Mock(status_code=500)
        mpost.return_value.raise_for_status.side_effect = Exception("boom")

        with self.assertRaises(Exception):
            send_notification.run("signal", "INFO", self._payload("retry"))

        self.assertTrue(mpost.called)

    @override_settings(NOTIFICATION_DEFAULTS={**BASE, "dry_run": False, "max_events_per_minute": 1})
    @patch("backend.tasks.notify.requests.post")
    def test_rate_limit_applies_per_minute(self, mpost: Mock):
        p1 = self._payload("rl-1")
        p2 = self._payload("rl-2")
        send_notification.run("signal", "INFO", p1)
        send_notification.run("signal", "INFO", p2)  # second may be rate-limited
        self.assertLessEqual(mpost.call_count, 1)

    @override_settings(NOTIFICATION_DEFAULTS={**BASE, "dry_run": False})
    @patch("backend.tasks.notify.requests.post")
    def test_dedup_same_bar_skips_second_send(self, mpost: Mock):
        ts = iso_now()
        p1 = {"symbol": "X", "timeframe": "1m", "bar_ts": ts, "title": "d1"}
        p2 = {"symbol": "X", "timeframe": "1m", "bar_ts": ts, "title": "d2"}  # identical bar
        send_notification.run("signal", "INFO", p1)
        send_notification.run("signal", "INFO", p2)
        self.assertEqual(mpost.call_count, 1)
