from __future__ import annotations
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver

class UserPreference(models.Model):
    id = models.SmallAutoField(primary_key=True)  # keep pk=1 singleton
    provider_order = models.CharField(max_length=128, default="AllTick")
    ml_blend_weight = models.FloatField(default=0.5)
    autoslowdown_enabled = models.BooleanField(default=True)
    thresholds = models.JSONField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return "UserPreference"

_PREFERENCES_CACHE_BUMP = 0

@receiver(post_save, sender=UserPreference)
def _bump_prefs_cache(*args, **kwargs):
    global _PREFERENCES_CACHE_BUMP
    _PREFERENCES_CACHE_BUMP += 1
