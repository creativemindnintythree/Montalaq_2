
from django.http import JsonResponse

from django.core.cache import cache

from django.db import connections


def healthz(_request):

    # Pure liveness: do NOT touch DB/Redis here.

    return JsonResponse({"status": "ok"}, status=200)


def readyz(_request):

    # Readiness: touch DB and cache/redis.

    out = {}


    # DB check

    try:

        with connections["default"].cursor() as c:

            c.execute("SELECT 1")

            c.fetchone()

        out["db"] = "ok"

    except Exception as e:

        out["db"] = f"error:{e.__class__.__name__}"


    # Cache/Redis check (works for any Django cache backend)

    try:

        key = "readyz_probe"

        cache.set(key, "1", 5)

        ok = cache.get(key) == "1"

        out["redis"] = "ok" if ok else "error:cache_miss"

    except Exception as e:

        out["redis"] = f"error:{e.__class__.__name__}"


    status = 200 if all(v == "ok" for v in out.values()) else 503

    return JsonResponse(out, status=status)

