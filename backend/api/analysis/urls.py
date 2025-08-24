# backend/api/analysis/urls.py
from django.urls import path
from .views import LatestAnalysisView, HistoryAnalysisView

urlpatterns = [
    # /api/analysis/latest?pair=EURUSD&tf=15m
    path("latest", LatestAnalysisView.as_view(), name="analysis-latest"),

    # /api/analysis/history?pair=EURUSD&tf=15m&limit=100
    path("history", HistoryAnalysisView.as_view(), name="analysis-history"),
]
