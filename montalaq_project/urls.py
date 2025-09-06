# montalaq_project/urls.py
from django.contrib import admin
from django.urls import path, include
from .health import readyz
from .health import healthz
from backend.api.schema import schema_view, redoc_view  # uses DRF get_schema_view + custom ReDoc

urlpatterns = [
    
    path('healthz', healthz, name='healthz'),
path("readyz", readyz),
    path("api/marketdata/", include("backend.api.marketdata.urls")),
    path("api/preferences/", include("backend.api.preferences.urls")),
    path("healthz", healthz),
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


from montalaq_project.health import healthz
