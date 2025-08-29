from django.utils.http import http_date, parse_http_date_safe
from django.utils.timezone import is_naive, make_naive
from datetime import timezone as dt_timezone
from django.core.exceptions import FieldError
from django.http import HttpResponseNotAllowed
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from hashlib import md5
from datetime import datetime

def _to_dt(v):
    if not v:
        return None
    if isinstance(v, datetime):
        return v if not is_naive(v) else v.replace(tzinfo=dt_timezone.utc)
    return None

class MarketDataLatestView(APIView):
    """
    GET /api/marketdata?pair=EURUSD&tf=15m
    Returns the latest ingestion slice for (pair, tf) with ETag/Last-Modified.
    """
    def get(self, request):
        pair = request.query_params.get("pair") or request.query_params.get("symbol")
        tf = request.query_params.get("tf") or request.query_params.get("timeframe")
        if not pair or not tf:
            return Response({"detail":"pair and tf are required"}, status=status.HTTP_400_BAD_REQUEST)

        from backend import models as m
        qs = None
        try:
            qs = m.IngestionStatus.objects.filter(symbol=pair, timeframe=tf)
        except (AttributeError, FieldError):
            try:
                qs = m.IngestionStatus.objects.filter(pair=pair, timeframe=tf)
            except Exception:
                qs = m.IngestionStatus.objects.none()

        row = qs.order_by("-last_ingest_ts").first()
        if not row:
            return Response({"detail":"not found"}, status=status.HTTP_404_NOT_FOUND)

        def g(obj, name, default=None):
            return getattr(obj, name, default)

        last_ing = _to_dt(g(row, "last_ingest_ts"))
        last_bar = _to_dt(g(row, "last_bar_ts"))
        provider = g(row, "provider", None)
        sym = g(row, "symbol", None) or g(row, "pair", pair)

        payload = {
            "symbol": sym,
            "timeframe": tf,
            "last_bar_ts": last_bar.isoformat().replace("+00:00","Z") if last_bar else None,
            "last_ingest_ts": last_ing.isoformat().replace("+00:00","Z") if last_ing else None,
            "provider": provider,
        }

        token = f"{sym}|{tf}|{payload['last_ingest_ts'] or ''}".encode("utf-8")
        etag = md5(token).hexdigest()
        inm = request.headers.get("If-None-Match")
        if inm and inm.strip('"') == etag:
            return Response(status=status.HTTP_304_NOT_MODIFIED, headers={"ETag": f"\"{etag}\""})

        headers = {"ETag": f"\"{etag}\""}
        if last_ing:
            lm = make_naive(last_ing, timezone=dt_timezone.utc)
            headers["Last-Modified"] = http_date(int(lm.timestamp()))
            ims = request.headers.get("If-Modified-Since")
            if ims:
                ts = parse_http_date_safe(ims)
                if ts is not None and int(lm.timestamp()) <= ts:
                    return Response(status=status.HTTP_304_NOT_MODIFIED, headers=headers)

        return Response(payload, headers=headers)

    def post(self, request):
        return HttpResponseNotAllowed(["GET"])
