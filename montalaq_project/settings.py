# montalaq_project/settings.py
from pathlib import Path
from celery.schedules import crontab

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = 'django-insecure-!zmdy93mw+)vfs)@tvp0uu#4i0*#36)ov7_box5@m+%0f9g$+l'
DEBUG = True
ALLOWED_HOSTS = []

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # Custom apps
    'backend',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'montalaq_project.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'montalaq_project.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'

# ---- Timezone hardening (Agent 011.3) ----
TIME_ZONE = 'Asia/Muscat'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# -----------------------------
# Celery configuration
# -----------------------------
CELERY_BROKER_URL = 'redis://localhost:6379/0'
CELERY_RESULT_BACKEND = 'redis://localhost:6379/0'
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'

# Align Celery with local timezone (TEMPORARY until Agent 013 orchestration)
CELERY_TIMEZONE = 'Asia/Muscat'
CELERY_ENABLE_UTC = False

# Import task modules so beat can find them
CELERY_IMPORTS = (
    "backend.tasks_ml_batch",
    # Add any other task modules that produce messages:
    "celery_tasks.preprocess_features",   # keep if module exists
)

# TEMPORARY beat schedule (Agent 011.3) — replace when Agent 013 delivers orchestration
CELERY_BEAT_SCHEDULE = {
    "agent0113-ml-batch-recent": {
        "task": "ml.batch_run_recent",
        # every 5 minutes
        "schedule": crontab(minute="*/5"),
        # args: limit, lookback_minutes
        "args": (50, 15),
    },
}

# Ensure Celery auto-discovers tasks in celery_tasks package
from montalaq_project.celery import app as celery_app  # noqa: E402
celery_app.autodiscover_tasks(['celery_tasks'])

# -----------------------------
# Logging for Ops (Agent 019)
# -----------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "compact": {
            "format": "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "compact",
        },
    },
    "loggers": {
        # Batch runner summary + errors
        "backend.tasks_ml_batch": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        # Celery worker/beat logs
        "celery": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": True,
        },
    },
}
