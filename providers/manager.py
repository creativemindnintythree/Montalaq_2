import os
from typing import List
from .alltick import AllTick
from .twelvedata_stub import TwelveData

_PROVIDER_REGISTRY = {
    "AllTick": AllTick,
    "TwelveData": TwelveData,
}

class ProviderManager:
    """Thin provider selector. Behavior remains AllTick-first unless changed later."""
    def __init__(self, order_env: str | None = None, allow_fallbacks_env: str | None = None):
        order_env = order_env or os.getenv("DEFAULT_PROVIDER_ORDER", "AllTick")
        self._order: List[str] = [p.strip() for p in order_env.split(",") if p.strip()]
        self._allow_fallbacks = (allow_fallbacks_env or os.getenv("ALLOW_FALLBACKS", "0")) in ("1", "true", "True")

    def get_order(self) -> List[str]:
        return [p for p in self._order if p in _PROVIDER_REGISTRY]

    def choose(self, symbol: str, timeframe: str):
        """Return the first configured provider instance (AllTick by default).
        Fallback logic is intentionally deferred to 012.2+.
        """
        order = self.get_order() or ["AllTick"]
        cls = _PROVIDER_REGISTRY[order[0]]
        return cls()

    def __repr__(self) -> str:
        return f"ProviderManager(order={self.get_order()}, allow_fallbacks={self._allow_fallbacks})"
