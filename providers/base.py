from typing import Any

class BaseProvider:
    name: str = "Base"

    def fetch_bar(self, symbol: str, timeframe: str) -> Any:
        """Return the latest bar for (symbol, timeframe).
        Implementations should raise NotImplementedError if not wired.
        """
        raise NotImplementedError("fetch_bar must be implemented by providers")
