# Make Celery load our task submodules when it imports `backend.tasks`
from .ingest_tasks import *      # registers @shared_task names
from .analysis_tasks import *
from .feature_tasks import *
from .scheduler import *
# freshness has no @shared_task, but importing doesn’t hurt
from .freshness import *
