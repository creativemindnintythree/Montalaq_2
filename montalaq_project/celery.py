import os
from celery import Celery
from celery.schedules import crontab

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "montalaq_project.settings")
app = Celery("montalaq_project")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

# TEMPORARY beat schedule (Agent 011.2 bridge)
app.conf.beat_schedule = {
    "ml-batch-every-5-min": {
        "task": "ml.batch_run_recent",
        "schedule": 300.0,  # every 5 minutes
        "args": (50, 10),   # limit=50 rows, scanned from last 10 minutes
    },
}
