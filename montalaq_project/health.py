from django.db import connections, DEFAULT_DB_ALIAS
from django.http import HttpResponse, JsonResponse

def healthz(request):
    return HttpResponse("ok", content_type="text/plain")

import os

def readyz(request):
    out, code = {}, 200
    try:
        conn = connections[DEFAULT_DB_ALIAS]
        with conn.cursor() as c:
            c.execute("SELECT 1")
        out["db"] = "ok"
    except Exception as e:
        out["db"] = f"error:{e.__class__.__name__}"
        code = 503

    try:
        import redis  # comes with Celery stack
        url = os.getenv("REDIS_URL") or os.getenv("CELERY_BROKER_URL", "")
        if url:
            r = redis.from_url(url, socket_connect_timeout=2, socket_timeout=2)
            r.ping()
            out["redis"] = "ok"
        else:
            out["redis"] = "skipped:no_url"
    except Exception as e:
        out["redis"] = f"error:{e.__class__.__name__}"
        code = 503

    return JsonResponse(out, status=code)
