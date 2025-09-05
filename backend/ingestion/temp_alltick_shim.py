# TEMPORARY: AllTick-only shim (remove when Agency 012 lands)
import os, datetime as dt, random
try:
    import requests
    from backend.net.retry import http_get_with_backoff  # only used when DEV_FAKE is off
except Exception:
    requests = None
    http_get_with_backoff = None  # type: ignore

ALLTICK_API_KEY = os.environ.get("ALLTICK_API_KEY")
DEV_FAKE = os.environ.get("ALLTICK_DEV_FAKE", "1")  # "1" = fake bars by default

def _now_utc():
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0)

def _dev_fake_bar(symbol: str, timeframe: str, last_close: float | None) -> dict:
    base = last_close if last_close is not None else 1.0000
    drift = (random.random() - 0.5) * 0.001  # ~±0.0005
    close = round(base + drift, 6)
    high = round(max(base, close) + 0.0003, 6)
    low  = round(min(base, close) - 0.0003, 6)
    open_ = base
    return {
        "symbol": symbol, "timeframe": timeframe, "timestamp": _now_utc(),
        "open": open_, "high": high, "low": low, "close": close,
        "volume": 0.0, "provider": "AllTick",
    }

def fetch_latest_bar(symbol: str, timeframe: str, last_close: float | None = None) -> dict:
    # Dev default: synthesize bars unless ALLTICK_DEV_FAKE=0
    if DEV_FAKE != "0":
        return _dev_fake_bar(symbol, timeframe, last_close)

    assert requests is not None, "requests not installed; pip install requests or set ALLTICK_DEV_FAKE=1"
    assert ALLTICK_API_KEY, "Missing ALLTICK_API_KEY; set it or use ALLTICK_DEV_FAKE=1"
    url = f"https://api.alltick.example/ohlcv?symbol={symbol}&tf={timeframe}&limit=1"
    headers = {"Authorization": f"Bearer {ALLTICK_API_KEY}"}
    r = http_get_with_backoff(url, headers=headers, timeout=10, max_attempts=5, base=0.2, factor=2.0, jitter=0.3)
    r.raise_for_status()
    j = r.json()[0]
    ts = dt.datetime.fromisoformat(j["ts"]).replace(tzinfo=dt.timezone.utc)
    return {
        "symbol": symbol, "timeframe": timeframe, "timestamp": ts,
        "open": j["o"], "high": j["h"], "low": j["l"], "close": j["c"],
        "volume": j["v"], "provider": "AllTick",
    }
