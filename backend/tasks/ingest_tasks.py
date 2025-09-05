import os
import datetime
from celery import shared_task
from django.utils.dateparse import parse_datetime
from django.utils import timezone
from django.db import transaction

from backend.models import MarketData, IngestionStatus
from backend.ingestion.temp_alltick_shim import fetch_latest_bar
from .utils import parse_watchlist, upsert_market_bar
from .freshness import update_ingestion_status
from backend.net.backoff_state import next_delay_seconds, until_from_now


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

    # Parse issued date for AllTick key (ISO8601) -> surface as key_age_days
    key_issued_at = os.getenv("ALLTICK_KEY_ISSUED_AT")
    key_age_days = None
    if key_issued_at:
        try:
            issued_dt = parse_datetime(key_issued_at)
            if issued_dt:
                import datetime as _dt
                key_age_days = (_dt.datetime.utcnow() - issued_dt.replace(tzinfo=None)).days
        except Exception:
            pass

    for sym in cfg["pairs"]:
        for tf in cfg["timeframes"]:
            # Load/create per-pair status row
            st, _ = IngestionStatus.objects.get_or_create(symbol=sym, timeframe=tf)

            # Gate on active backoff
            if st.in_backoff and st.backoff_until and timezone.now() < st.backoff_until:
                continue

            try:
                bar = fetch_latest_bar(sym, tf, last_close=_last_close(sym, tf))
                if not bar:
                    continue

                # Ensure provider attribution is present on MarketData
                bar["provider"] = "AllTick"

                # Upsert + status update atomically
                with transaction.atomic():
                    upsert_market_bar(bar)
                    status = update_ingestion_status(sym, tf)
                    if status:
                        status.provider = "AllTick"
                        status.fallback_active = False
                        if key_age_days is not None:
                            status.key_age_days = key_age_days
                        status.save()

                    # Clear backoff on success
                    st.in_backoff = False
                    st.backoff_attempts = 0
                    st.backoff_until = None
                    st.last_ingest_ts = timezone.now()
                    st.save(update_fields=["in_backoff","backoff_attempts","backoff_until","last_ingest_ts"])

            except Exception:
                # Failure: increment attempts, compute next delay, set backoff
                st.backoff_attempts = (st.backoff_attempts or 0) + 1
                delay = next_delay_seconds(max(0, st.backoff_attempts - 1))
                st.in_backoff = True
                st.backoff_until = until_from_now(delay)
                st.save(update_fields=["in_backoff","backoff_attempts","backoff_until"])
                # continue to next (symbol,timeframe)
                continue

