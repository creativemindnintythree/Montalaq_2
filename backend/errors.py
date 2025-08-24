# backend/errors.py
"""
Unified orchestration error taxonomy for Agencies 013.x / 016.x

- A single Enum (ErrorCode) used across tasks, views, and model helpers.
- Stable string values so logs, dashboards, and tests don’t break.
- A central EXCEPTION_MAP to translate common exceptions → canonical codes.
- Compatible with 013.2.1 expectations: `from backend.errors import ErrorCode, EXCEPTION_MAP, map_exception`.

Docs: add/maintain a short reference at `/docs/audit/error_codes.md`
covering each code below and where it is raised.
"""

from __future__ import annotations

from enum import Enum
from typing import Dict, Type

# Optional cross‑DB IntegrityError mapping
try:
    from django.db.utils import IntegrityError as DjangoIntegrityError  # type: ignore
except Exception:  # pragma: no cover
    DjangoIntegrityError = None  # type: ignore

try:
    from sqlite3 import IntegrityError as SQLiteIntegrityError  # type: ignore
except Exception:  # pragma: no cover
    SQLiteIntegrityError = None  # type: ignore


class ErrorCode(str, Enum):
    # ---- 013.4 additions (runbook emphasis) ----
    DUPLICATE_WRITE = "E0134_DUPLICATE"      # Attempted to create a duplicate TradeAnalysis (idempotency violation)
    NO_TRADE_SKIP   = "E0134_NO_TRADE_SKIP"  # Analysis intentionally skipped because rules decided NO_TRADE
    STALE_DATA      = "E0134_STALE"          # Freshness gate not GREEN (AMBER/RED)
    HEARTBEAT_MISS  = "E0134_HEARTBEAT"      # No recent heartbeat; connected vs. stale ambiguity

    # ---- Legacy / shared orchestration codes (kept for compatibility with 013.2/013.3 tests) ----
    INGESTION_TIMEOUT          = "INGESTION_TIMEOUT"
    PROVIDER_DISCONNECTED      = "PROVIDER_DISCONNECTED"
    DUPLICATE_TICK             = "DUPLICATE_TICK"
    FRESHNESS_THRESHOLD_EXCEEDED = "FRESHNESS_THRESHOLD_EXCEEDED"
    ANALYSIS_ERR               = "ANALYSIS_ERR"  # Generic rules/ML/composite runtime error
    UNKNOWN                    = "UNKNOWN"


# Map common exception *types* to canonical codes.
# NOTE: Prefer mapping by exception class here; map by context-specific logic in callers if needed.
EXCEPTION_MAP: Dict[Type[BaseException], ErrorCode] = {
    TimeoutError: ErrorCode.INGESTION_TIMEOUT,
    ConnectionError: ErrorCode.PROVIDER_DISCONNECTED,
    RuntimeError: ErrorCode.ANALYSIS_ERR,  # generic compute/ML runtime
    ValueError: ErrorCode.ANALYSIS_ERR,    # bad inputs, parsing, etc.
}

# Add IntegrityError mappings if available (DB duplicate writes, unique constraints)
if DjangoIntegrityError is not None:
    EXCEPTION_MAP[DjangoIntegrityError] = ErrorCode.DUPLICATE_WRITE  # type: ignore[index]
if SQLiteIntegrityError is not None:
    EXCEPTION_MAP[SQLiteIntegrityError] = ErrorCode.DUPLICATE_WRITE  # type: ignore[index]


def map_exception(exc: BaseException) -> ErrorCode:
    """
    Return the canonical ErrorCode for a given exception instance.
    Falls back to ErrorCode.UNKNOWN if the type is not in EXCEPTION_MAP.
    """
    return EXCEPTION_MAP.get(type(exc), ErrorCode.UNKNOWN)


# Convenience helpers for callers that need explicit, readable constants
def stale_code() -> str:
    """String value for 'freshness not GREEN' situations (scheduler gating, API surfacing)."""
    return ErrorCode.STALE_DATA.value


def no_trade_skip_code() -> str:
    """String value used when rules return NO_TRADE and the task intentionally avoids persistence."""
    return ErrorCode.NO_TRADE_SKIP.value


def duplicate_write_code() -> str:
    """String value for DB unique‑constraint collisions on idempotent keys."""
    return ErrorCode.DUPLICATE_WRITE.value


def heartbeat_miss_code() -> str:
    """String value for heartbeat gaps (quiet vs. broken feed heuristics)."""
    return ErrorCode.HEARTBEAT_MISS.value
