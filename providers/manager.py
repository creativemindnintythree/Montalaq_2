import os
from typing import List
from .alltick import AllTick
from .twelvedata_stub import TwelveData

from time import monotonic
try:
    from backend.preferences.models import UserPreference, _PREFERENCES_CACHE_BUMP
except Exception:
    UserPreference = None
    _PREFERENCES_CACHE_BUMP = 0

_PROVIDER_REGISTRY = {
    "AllTick": AllTick,
    "TwelveData": TwelveData,
}

_CACHE_TTL_S = 5.0
_last_fetch_t = 0.0
_last_bump = -1
_cached_order = None

def _db_order_or_none():
    global _last_fetch_t, _last_bump, _cached_order
    now = monotonic()
    try:
        bump = _PREFERENCES_CACHE_BUMP
    except Exception:
        bump = -1
    if _cached_order is not None and (now - _last_fetch_t) < _CACHE_TTL_S and bump == _last_bump:
        return _cached_order
    if UserPreference is None:
        return None
    try:
        obj = UserPreference.objects.filter(pk=1).first()
        if obj and obj.provider_order:
            _cached_order = [p.strip() for p in obj.provider_order.split(",") if p.strip()]
        else:
            _cached_order = None
    except Exception:
        _cached_order = None
    _last_fetch_t = now
    _last_bump = bump
    return _cached_order

class ProviderManager:
    """Thin provider selector. Behavior remains AllTick-first unless changed later."""
    def __init__(self, order_env: str | None = None, allow_fallbacks_env: str | None = None):
        order_env = order_env or os.getenv("DEFAULT_PROVIDER_ORDER", "AllTick")
        self._order: List[str] = [p.strip() for p in order_env.split(",") if p.strip()]
        self._allow_fallbacks = (allow_fallbacks_env or os.getenv("ALLOW_FALLBACKS", "0")) in ("1", "true", "True")

    def get_order(self) -> List[str]:
        db_order = _db_order_or_none()
        src = db_order if db_order else self._order
        return [p for p in src if p in _PROVIDER_REGISTRY]

    def choose(self, symbol: str, timeframe: str):
        """Return the first configured provider instance (AllTick by default).
        Fallback logic is intentionally deferred to 012.2+.
        """
        order = self.get_order() or ["AllTick"]
        cls = _PROVIDER_REGISTRY[order[0]]
        return cls()

    def __repr__(self) -> str:
        return f"ProviderManager(order={self.get_order()}, allow_fallbacks={self._allow_fallbacks})"
