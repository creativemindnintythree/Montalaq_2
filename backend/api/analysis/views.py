# backend/api/analysis/views.py
from django.apps import apps
from django.core.cache import cache
from django.conf import settings
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from backend.api.analysis.serializers import (
    LatestAnalysisSerializer,
    HistoryAnalysisSerializer,
)

TradeAnalysis = apps.get_model("backend", "TradeAnalysis")


class LatestAnalysisView(APIView):
    """
    GET /api/analysis/latest?pair=EURUSD&tf=1m
    Returns the most recent TradeAnalysis row for the given pair/timeframe.
    """

    def get(self, request, *args, **kwargs):
        pair = request.query_params.get("pair")
        tf = request.query_params.get("tf")

        if not pair or not tf:
            return Response(
                {"error": "Missing required query params: pair, tf"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        cache_key = f"analysis:latest:{pair}:{tf}"
        cached = cache.get(cache_key)
        if cached:
            return Response(cached)

        obj = (
            TradeAnalysis.objects.filter(
                market_data_feature__market_data__symbol=pair,
                market_data_feature__market_data__timeframe=tf,
            )
            .order_by("-timestamp")
            .first()
        )
        if not obj:
            return Response({"error": "No analysis found"}, status=status.HTTP_404_NOT_FOUND)

        data = LatestAnalysisSerializer(obj).data
        cache.set(cache_key, data, getattr(settings, "ANALYSIS_API_CACHE_TTL", 30))
        return Response(data)


class HistoryAnalysisView(APIView):
    """
    GET /api/analysis/history?pair=EURUSD&tf=1m&limit=100
    Returns multiple past TradeAnalysis rows.
    """

    def get(self, request, *args, **kwargs):
        pair = request.query_params.get("pair")
        tf = request.query_params.get("tf")
        try:
            limit = int(request.query_params.get("limit", "100"))
        except ValueError:
            limit = 100

        if not pair or not tf:
            return Response(
                {"error": "Missing required query params: pair, tf"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        cache_key = f"analysis:history:{pair}:{tf}:{limit}"
        cached = cache.get(cache_key)
        if cached:
            return Response(cached)

        qs = (
            TradeAnalysis.objects.filter(
                market_data_feature__market_data__symbol=pair,
                market_data_feature__market_data__timeframe=tf,
            )
            .order_by("-timestamp")[:limit]
        )
        if not qs.exists():
            return Response({"error": "No analysis found"}, status=status.HTTP_404_NOT_FOUND)

        data = HistoryAnalysisSerializer(qs, many=True).data
        cache.set(cache_key, data, getattr(settings, "ANALYSIS_API_CACHE_TTL", 30))
        return Response(data)
