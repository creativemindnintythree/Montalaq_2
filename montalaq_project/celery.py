# montalaq_project/celery.py
import os
from celery import Celery
from django.conf import settings

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "montalaq_project.settings")

app = Celery("montalaq_project")
app.config_from_object("django.conf:settings", namespace="CELERY")

# Autodiscover tasks from installed apps
app.autodiscover_tasks(["backend", "celery_tasks"])

# Ensure key modules are imported so @shared_task registers
try:
    from backend.tasks import scheduler as _scheduler  # noqa: F401
except Exception:
    # Safe to continue; tasks may still be found via autodiscover
    pass

# Pin Beat DB so we know which file is used
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
app.conf.beat_schedule_filename = os.path.join(BASE_DIR, "celerybeat-schedule")

# ---- Beat schedule (settings-driven) ----------------------------------------
# NOTE:
# * 0131 scheduler tick remains at 60s by default here.
# * KPI rollup is attached via celery_tasks/rollup_kpis.py (@app.on_after_configure)
#   to avoid duplicate scheduling; we intentionally DO NOT add a static KPI entry.
app.conf.beat_schedule = {
    "0131-tick-every-60s": {
        "task": "backend.tasks.scheduler.tick",
        "schedule": 60.0,
    },
}

# Add escalation / breaker entries using settings (no hard-coded 60s)
# Use .update so it plays nicely if other code adds schedule entries, too.
app.conf.beat_schedule.update({
    "escalation-eval": {
        # Match the task name implemented in backend/tasks/escalation.py
        # If your task name is different, adjust here accordingly.
        "task": "backend.tasks.escalation.evaluate_escalations",
        "schedule": getattr(settings, "ESCALATION_EVAL_INTERVAL_SEC", 60),
    },
    "circuit-breaker": {
        # This should point at your breaker tick task if/when added.
        "task": "backend.tasks.escalation.circuit_breaker_tick",
        "schedule": getattr(settings, "CIRCUIT_BREAKER_INTERVAL_SEC", 60),
    },
})
