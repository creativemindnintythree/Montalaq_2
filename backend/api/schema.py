# backend/api/schema.py
from __future__ import annotations

from django.http import HttpResponse
from django.urls import reverse
from rest_framework.schemas import get_schema_view

# -----------------------------------------------------------------------------
# OpenAPI schema (JSON)
# Expose this in urls.py with:
#   path("openapi-schema", schema_view, name="openapi-schema"),
# -----------------------------------------------------------------------------
schema_view = get_schema_view(
    title="Montalaq API",
    description=(
        "Public endpoints for Montalaq 2.0\n\n"
        "• Ingestion Status: /api/ingestion/status\n"
        "• Analysis: /api/analysis/latest, /api/analysis/history\n\n"
        "Notes:\n"
        "– Fields reflect Agency 013.2/013.3 contracts (provider, escalation_level, "
        "  breaker_open, KPIs, etc.).\n"
        "– Some responses may be cached.\n"
    ),
    version="v0",
    public=True,
)

# -----------------------------------------------------------------------------
# ReDoc UI (HTML) — no extra templates required
# Expose this in urls.py with:
#   path("redoc/", redoc_view, name="redoc"),
# -----------------------------------------------------------------------------
def redoc_view(request):
    """
    Minimal ReDoc page that points to the named 'openapi-schema' route.
    No template files or extra dependencies are needed.
    """
    schema_url = request.build_absolute_uri(reverse("openapi-schema"))
    html = f"""<!DOCTYPE html>
<html>
  <head>
    <meta charset="utf-8"/>
    <title>Montalaq API — ReDoc</title>
    <meta name="viewport" content="width=device-width, initial-scale=1"/>
    <style>
      html, body, #redoc {{ height: 100%; margin: 0; padding: 0; }}
    </style>
    <script src="https://cdn.redoc.ly/redoc/latest/bundles/redoc.standalone.js"></script>
  </head>
  <body>
    <redoc id="redoc" spec-url="{schema_url}"></redoc>
  </body>
</html>"""
    return HttpResponse(html)
