from .alert_tasks import *     # notifications
# backend/tasks/__init__.py
"""
Expose Celery tasks by importing submodules so Celery can register them
when it imports `backend.tasks`.
"""

# --- Task modules (export @shared_task callables) ---
from .ingest_tasks import *       # ingestion pipeline tasks
from .analysis_tasks import *     # rules/ML/composite analysis tasks
from .feature_tasks import *      # feature engineering tasks
from .scheduler import *          # periodic tick / orchestration
from .escalation import *         # escalation ladder & circuit breaker tasks

# --- Helper modules (no @shared_task, safe to import) ---
from .freshness import *          # freshness + KPI helpers (returns model instance)

# NOTE:
# We intentionally DO NOT import `.kpis` here to avoid registering legacy
# tasks like `backend.tasks.kpis.rollup_5m`. KPI scheduling is handled by
# `celery_tasks/rollup_kpis.py` per 013.2.1 so we don't double-schedule.
