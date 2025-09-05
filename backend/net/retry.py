import random, time
from typing import Iterable, Optional, Tuple
import requests

RETRY_STATUS: Tuple[int, ...] = (429, 500, 502, 503, 504)

def http_get_with_backoff(
    url: str,
    *,
    headers: Optional[dict] = None,
    timeout: float = 10.0,
    max_attempts: int = 5,
    base: float = 0.25,
    factor: float = 2.0,
    jitter: float = 0.25,
    retry_status: Iterable[int] = RETRY_STATUS,
):
    """
    Lightweight bounded exponential backoff with full jitter.
    Retries on connect/read timeouts and on retryable HTTP status codes.
    """
    last_exc = None
    for attempt in range(1, max_attempts + 1):
        try:
            r = requests.get(url, headers=headers or {}, timeout=timeout)
            if r.status_code not in retry_status:
                return r
            last_exc = RuntimeError(f"HTTP {r.status_code}")
        except (requests.Timeout, requests.ConnectionError) as e:
            last_exc = e
        # sleep if we will retry
        if attempt < max_attempts:
            sleep_s = base * (factor ** (attempt - 1)) + random.uniform(0, jitter)
            time.sleep(sleep_s)
    # give up
    if last_exc:
        raise last_exc
    raise RuntimeError("http_get_with_backoff: exhausted attempts")
