import os
from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "montalaq_project.settings")

app = Celery("montalaq_project")
app.config_from_object("django.conf:settings", namespace="CELERY")

# Autodiscover tasks from installed apps
app.autodiscover_tasks(["backend", "celery_tasks"])

# Ensure KPI and scheduler modules are imported so @shared_task registers
try:
    from backend.tasks import scheduler as _scheduler  # noqa: F401
    from backend.tasks import kpis as _kpis  # noqa: F401
except Exception:
    pass

# Pin Beat DB so we know which file is used
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
app.conf.beat_schedule_filename = os.path.join(BASE_DIR, "celerybeat-schedule")

app.conf.beat_schedule = {
    "0131-tick-every-60s": {
        "task": "backend.tasks.scheduler.tick",
        "schedule": 60.0,
    },
    "0132-kpi-rollup-60s": {
        "task": "backend.tasks.kpis.rollup_5m",
        "schedule": 60.0,
    },
}
