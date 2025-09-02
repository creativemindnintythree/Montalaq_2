from django.urls import path
from .views import IngestionStatusView

urlpatterns = [
    path("status", IngestionStatusView.as_view(), name="ingestion-status"),
    path("status/", IngestionStatusView.as_view()),
]
