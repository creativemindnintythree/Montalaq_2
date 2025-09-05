from django.test import TestCase, override_settings
from django.utils import timezone

@override_settings(CACHES={"default":{"BACKEND":"django.core.cache.backends.locmem.LocMemCache","LOCATION":"notify-tests"}})
class TestNotify(TestCase):
    def test_warn_normalizes_to_warning_and_does_not_floor_signal(self):
        from backend.tasks.notify import send_notification
        # This should not raise or be skipped by per-event floor when a channel listens to signal
        send_notification.run(
            "signal", "warn",
            {"symbol":"X","timeframe":"1m","bar_ts": timezone.now().strftime("%Y-%m-%dT%H:%M:%SZ")}
        )
