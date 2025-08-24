# syntax=docker/dockerfile:1.7
FROM python:3.13-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# System deps (timezone & build tools kept minimal)
RUN apt-get update -y && apt-get install -y --no-install-recommends \
    gcc curl tzdata \
    && rm -rf /var/lib/apt/lists/*

# If you have a requirements.txt, copy & install that first for layer caching.
# Otherwise, fall back to safe minimums for this project.
COPY requirements.txt /app/requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip \
    if [ -f requirements.txt ]; then \
      pip install -r requirements.txt; \
    else \
      pip install "Django>=5.0,<6.0" "djangorestframework>=3.15,<3.16" \
                  "celery>=5.3,<5.6" "redis>=5.0,<6.0" "drf-yasg>=1.21,<1.22" \
                  "gunicorn>=21.2,<22.0"; \
    fi

# Project code
COPY . /app

# Entrypoints
COPY docker/entrypoint.web.sh   /usr/local/bin/entrypoint.web.sh
COPY docker/entrypoint.worker.sh /usr/local/bin/entrypoint.worker.sh
COPY docker/entrypoint.beat.sh   /usr/local/bin/entrypoint.beat.sh
RUN chmod +x /usr/local/bin/entrypoint.*.sh

# Default to web (can be overridden by compose)
CMD ["entrypoint.web.sh"]
