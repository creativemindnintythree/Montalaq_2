# montalaq_project/urls.py
from django.contrib import admin
from django.urls import path, include
from backend.api.schema import schema_view, redoc_view  # uses DRF get_schema_view + custom ReDoc

urlpatterns = [
    path("admin/", admin.site.urls),

    # ---- API schema & docs ----
    # Raw OpenAPI JSON
    path("openapi-schema", schema_view, name="openapi-schema"),
    # ReDoc UI (served via our lightweight HTML view)
    path("redoc/", redoc_view, name="redoc"),

    # ---- Core APIs ----
    path("api/ingestion/", include("backend.api.status.urls")),   # /api/ingestion/status
    path("api/analysis/", include("backend.api.analysis.urls")),  # /api/analysis/latest, /history
]
