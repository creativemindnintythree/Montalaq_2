
from django.db import models


def _alias_timestamp(kwargs: dict) -> dict:

    if "timestamp" in kwargs and "bar_ts" not in kwargs:

        kwargs = dict(kwargs)

        kwargs["bar_ts"] = kwargs.pop("timestamp")

    return kwargs


class TradeAnalysisManager(models.Manager):

    def create(self, **kwargs):

        return super().create(**_alias_timestamp(kwargs))


    def get_or_create(self, defaults=None, **kwargs):

        kwargs = _alias_timestamp(kwargs)

        if defaults:

            defaults = _alias_timestamp(defaults)

        return super().get_or_create(defaults=defaults, **kwargs)


    def update_or_create(self, defaults=None, **kwargs):

        kwargs = _alias_timestamp(kwargs)

        if defaults:

            defaults = _alias_timestamp(defaults)

        return super().update_or_create(defaults=defaults, **kwargs)

