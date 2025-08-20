# tests/conftest.py
import os
import pytest

@pytest.fixture(autouse=True)
def _isolate_settings(settings, monkeypatch):
    # keep real DB so we use your actual migrations; just make Celery synchronous & quiet
    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.CELERY_TASK_EAGER_PROPAGATES = True
    settings.CELERY_BROKER_URL = "memory://"
    settings.CELERY_RESULT_BACKEND = "cache+memory://"

    # quiet logs (optional)
    settings.LOGGING = {}

    # make any “fetcher” code know we’re in tests
    monkeypatch.setenv("RUNNING_TESTS", "1")
    monkeypatch.setenv("EODHD_API_KEY", "TEST_ONLY")

    return settings
