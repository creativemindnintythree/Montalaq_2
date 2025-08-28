"""
Django settings for montalaq_project.
"""

import os
from pathlib import Path

# =========================
# Core paths & switches
# =========================
BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv("SECRET_KEY", "dev-insecure-key")
DEBUG = os.getenv("DEBUG", "1") == "1"
ALLOWED_HOSTS = os.getenv("ALLOWED_HOSTS", "*").split(",")

TIME_ZONE = os.getenv("TIMEZONE", "UTC")
USE_TZ = True
USE_I18N = True
LANGUAGE_CODE = "en-us"

# =========================
# Installed apps / middleware
# =========================
INSTALLED_APPS = [
    # Django
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    # Third-party
    "rest_framework",          # DRF
    "drf_yasg",                # Swagger / Redoc

    # Project apps
    "backend",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "montalaq_project.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],  # keep if you add templates later
        "NAME": "django",
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "montalaq_project.wsgi.application"

# =========================
# Database (SQLite default)
# =========================
SQLITE_PATH = os.getenv("SQLITE_PATH", str(BASE_DIR / "db.sqlite3"))
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": SQLITE_PATH,
    }
}
# (If/when you switch to Postgres, wire DATABASE_URL + dj-database-url here.)

# =========================
# Static / media
# =========================
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [
    BASE_DIR / "static",
]

# =========================
# DRF (defaults are fine)
# =========================
REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
        # Add BrowsableAPIRenderer in dev if you want:
        # "rest_framework.renderers.BrowsableAPIRenderer",
    ],
    "DEFAULT_PARSER_CLASSES": [
        "rest_framework.parsers.JSONParser",
    ],
}

# =========================
# Celery / Redis
# =========================
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", REDIS_URL)
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", REDIS_URL)

# Optional but handy tunables (picked up in your Celery app/entrypoints)
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_ALWAYS_EAGER = False
CELERY_TASK_QUEUES = None  # default queue 'celery'
CELERY_WORKER_CONCURRENCY = int(os.getenv("CELERY_CONCURRENCY", "4"))
CELERY_WORKER_MAX_TASKS_PER_CHILD = int(os.getenv("CELERY_MAX_TASKS_PER_CHILD", "100"))
CELERY_WORKER_PREFETCH_MULTIPLIER = int(os.getenv("CELERY_PREFETCH_MULTIPLIER", "4"))
# You can enable these later if desired:
# CELERY_TASK_ACKS_LATE = os.getenv("CELERY_TASK_ACKS_LATE", "0") == "1"
# CELERY_TASK_TIME_LIMIT = int(os.getenv("CELERY_TASK_TIME_LIMIT", "0") or 0) or None
# CELERY_TASK_SOFT_TIME_LIMIT = int(os.getenv("CELERY_TASK_SOFT_TIME_LIMIT", "0") or 0) or None

# =========================
# Provider API keys & order
# =========================
ALLTICK_API_KEY = os.getenv("ALLTICK_API_KEY", "")
TWELVEDATA_API_KEY = os.getenv("TWELVEDATA_API_KEY", "")

DEFAULT_PROVIDER_ORDER = os.getenv("DEFAULT_PROVIDER_ORDER", "AllTick")
ALLOW_FALLBACKS = os.getenv("ALLOW_FALLBACKS", "0") == "1"
AUTOSLOWDOWN = os.getenv("AUTOSLOWDOWN", "1") == "1"

# =========================
# Freshness / heartbeat tunables (used by freshness/serializer logic)
# =========================
EXPECTED_INTERVALS = {
    "1m": int(os.getenv("EXPECTED_INTERVAL_1m", "60")),
    "15m": int(os.getenv("EXPECTED_INTERVAL_15m", "1800")),
    "1h": int(os.getenv("EXPECTED_INTERVAL_1h", "5400")),
    "4h": int(os.getenv("EXPECTED_INTERVAL_4h", "21600")),
}

# =========================
# Logging
# =========================
DJANGO_LOG_LEVEL = os.getenv("DJANGO_LOG_LEVEL", "INFO")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "console": {
            "format": "[%(asctime)s] %(levelname)s %(name)s: %(message)s",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "console",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": DJANGO_LOG_LEVEL,
    },
}

# =========================
# Security (prod hardening toggles; safe in dev)
# =========================
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
