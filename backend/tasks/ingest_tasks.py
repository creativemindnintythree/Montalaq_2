import os
import datetime
from celery import shared_task
from django.utils.dateparse import parse_datetime

from backend.models import MarketData
from backend.ingestion.temp_alltick_shim import fetch_latest_bar
from .utils import parse_watchlist, upsert_market_bar
from .freshness import update_ingestion_status


def _last_close(symbol: str, timeframe: str):
    row = (
        MarketData.objects.filter(symbol=symbol, timeframe=timeframe)
        .order_by("-timestamp")
        .values("close")
        .first()
    )
    return row["close"] if row else None


@shared_task(rate_limit="10/s")
def ingest_once():
    cfg = parse_watchlist()

    # Parse issued date for AllTick key (ISO8601)
    key_issued_at = os.getenv("ALLTICK_KEY_ISSUED_AT")
    key_age_days = None
    if key_issued_at:
        try:
            issued_dt = parse_datetime(key_issued_at)
            if issued_dt:
                key_age_days = (datetime.datetime.utcnow() - issued_dt.replace(tzinfo=None)).days
        except Exception:
            pass

    for sym in cfg["pairs"]:
        for tf in cfg["timeframes"]:
            bar = fetch_latest_bar(sym, tf, last_close=_last_close(sym, tf))
            if not bar:
                continue

            # Ensure provider attribution is present on MarketData
            bar["provider"] = "AllTick"

            # Upsert bar into DB (filters out non-MarketData fields)
            upsert_market_bar(bar)

            # Update ingestion status (AllTick-specific metadata)
            status = update_ingestion_status(sym, tf)
            if status:
                status.provider = "AllTick"
                status.fallback_active = False  # status-only field, not MarketData
                if key_age_days is not None:
                    status.key_age_days = key_age_days
                status.save()
