import os
from celery import Celery
from celery.schedules import crontab

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "montalaq_project.settings")

app = Celery("montalaq_project")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

# Beat schedules
app.conf.beat_schedule = {
    # ✅ 013.1 spine: run full tick every 60s (ingest → freshness → analyze)
    "0131-tick-every-60s": {
        "task": "backend.tasks.scheduler.tick",
        "schedule": 60.0,
    },

    # (existing) TEMPORARY ML batch schedule (Agent 011.2 bridge)
    "ml-batch-every-5-min": {
        "task": "ml.batch_run_recent",
        "schedule": 300.0,  # every 5 minutes
        "args": (50, 10),   # limit=50 rows, scanned from last 10 minutes
    },
}
