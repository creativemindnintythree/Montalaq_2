# backend/api/status/urls.py
from django.urls import path
from .views import IngestionStatusView

urlpatterns = [
    # Final endpoint: /api/ingestion/status   (no trailing slash)
    path("status", IngestionStatusView.as_view(), name="ingestion-status"),

    # Also accept a trailing slash just in case
    path("status/", IngestionStatusView.as_view()),
]
