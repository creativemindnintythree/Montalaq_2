# backend/api/status/urls.py

from django.urls import path
from .views import IngestionStatusView

urlpatterns = [
    path("api/ingestion/status", IngestionStatusView.as_view(), name="ingestion-status"),
]
