from __future__ import annotations
import os, random
from datetime import timedelta, datetime, timezone

# Dev-profile knobs (override via env if needed)
BASE   = float(os.getenv("BACKOFF_BASE_SEC",   "0.5"))
FACTOR = float(os.getenv("BACKOFF_FACTOR",     "2.0"))
CAP    = float(os.getenv("BACKOFF_CAP_SEC",    "30.0"))
JITTER = float(os.getenv("BACKOFF_JITTER",     "0.2"))  # ±20%

def next_delay_seconds(attempts: int) -> float:
    """
    Bounded exponential backoff with full jitter.
    attempts: non-negative int (0 for first failure)
    """
    attempts = max(0, int(attempts))
    raw = min(CAP, BASE * (FACTOR ** attempts))
    jitter = 1.0 + random.uniform(-JITTER, JITTER)
    return max(0.0, raw * jitter)

def until_from_now(seconds: float) -> datetime:
    return datetime.now(timezone.utc) + timedelta(seconds=max(0.0, float(seconds)))
