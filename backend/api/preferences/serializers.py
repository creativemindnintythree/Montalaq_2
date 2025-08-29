from rest_framework import serializers
from backend.preferences.models import UserPreference

class UserPreferenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserPreference
        fields = ("provider_order","ml_blend_weight","autoslowdown_enabled","thresholds","updated_at")
