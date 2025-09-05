# backend/api/analysis/serializers.py
from __future__ import annotations

from typing import Any, Dict, Optional

from django.apps import apps
from rest_framework import serializers


TradeAnalysis = apps.get_model("backend", "TradeAnalysis")


class _TradeAnalysisBaseSerializer(serializers.ModelSerializer):
    """
    Shared fields/helpers for latest/history views.
    Exposes symbol/timeframe via related MarketData, plus optional top_features.
    """
    symbol = serializers.SerializerMethodField()
    timeframe = serializers.SerializerMethodField()
    bar_ts = serializers.SerializerMethodField()
    top_features = serializers.SerializerMethodField()
    stop_loss = serializers.SerializerMethodField()
    take_profit = serializers.SerializerMethodField()

    class Meta:
        model = TradeAnalysis
        fields = (
            "symbol",
            "timeframe",
            "bar_ts",
            "status",
            "final_decision",
            "rule_confidence_score",
            "ml_confidence",
            "composite_score",
            "stop_loss",
            "take_profit",
            "error_code",
            "error_message",
            "top_features",          # optional (Agency 011 stored it)
        )

    def get_symbol(self, obj) -> Optional[str]:
        try:
            return obj.market_data_feature.market_data.symbol
        except Exception:
            return None

    def get_timeframe(self, obj) -> Optional[str]:
        try:
            return obj.market_data_feature.market_data.timeframe
        except Exception:
            return None

    def get_bar_ts(self, obj):
        # Prefer the TA.timestamp; model.save aligns this to the bar
        return getattr(obj, "bar_ts", None)

    
    def get_stop_loss(self, obj):
        try:
            return getattr(obj, "sl", None)
        except Exception:
            return None

    def get_take_profit(self, obj):
        try:
            return getattr(obj, "tp", None)
        except Exception:
            return None

    def get_top_features(self, obj) -> Optional[Dict[str, Any]]:
        """
        If Agency 011 stored explainability, expose it as-is.
        Accepts either obj.top_features (013.3) or obj.feature_importances (older 011).
        """
        if getattr(obj, "top_features", None) is not None:
            return obj.top_features
        if getattr(obj, "feature_importances", None) is not None:
            return obj.feature_importances
        return None


class LatestAnalysisSerializer(_TradeAnalysisBaseSerializer):
    """Single latest record payload."""
    class Meta(_TradeAnalysisBaseSerializer.Meta):
        pass


class HistoryAnalysisSerializer(_TradeAnalysisBaseSerializer):
    """History list payload (e.g., for a time range)."""
    class Meta(_TradeAnalysisBaseSerializer.Meta):
        pass
