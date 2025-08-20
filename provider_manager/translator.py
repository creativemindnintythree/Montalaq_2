# C:\Users\AHMED AL BALUSHI\Montalaq_2\provider_manager\translator.py

from datetime import datetime

def translate_market_data(provider_name, raw_response):
    """
    Normalize each provider's OHLCV + ATR(14) response to unified schema.
    Fields: timestamp, open, high, low, close, volume, atr_14, provider
    """
    results = []

    if provider_name == "finnhub":
        if all(k in raw_response for k in ["t", "o", "h", "l", "c", "v"]):
            for i in range(len(raw_response["t"])):
                results.append({
                    "timestamp": datetime.utcfromtimestamp(raw_response["t"][i]),
                    "open": raw_response["o"][i],
                    "high": raw_response["h"][i],
                    "low": raw_response["l"][i],
                    "close": raw_response["c"][i],
                    "volume": raw_response["v"][i],
                    "atr_14": None,  # Finnhub does not return ATR by default
                    "provider": "finnhub"
                })

    elif provider_name == "twelvedata":
        if "values" in raw_response:
            for item in raw_response["values"]:
                results.append({
                    "timestamp": datetime.strptime(item["datetime"], "%Y-%m-%d %H:%M:%S"),
                    "open": float(item["open"]),
                    "high": float(item["high"]),
                    "low": float(item["low"]),
                    "close": float(item["close"]),
                    "volume": float(item["volume"]),
                    "atr_14": float(item.get("atr", 0.0)) if "atr" in item else None,
                    "provider": "twelvedata"
                })

    elif provider_name == "allticks":
        if "data" in raw_response:
            for item in raw_response["data"]:
                results.append({
                    "timestamp": datetime.strptime(item["timestamp"], "%Y-%m-%dT%H:%M:%S"),
                    "open": float(item["open"]),
                    "high": float(item["high"]),
                    "low": float(item["low"]),
                    "close": float(item["close"]),
                    "volume": float(item["volume"]),
                    "atr_14": None,
                    "provider": "allticks"
                })

    elif provider_name == "eodhd":
        if isinstance(raw_response, list):
            for item in raw_response:
                results.append({
                    "timestamp": datetime.strptime(item["datetime"], "%Y-%m-%d %H:%M:%S"),
                    "open": float(item["open"]),
                    "high": float(item["high"]),
                    "low": float(item["low"]),
                    "close": float(item["close"]),
                    "volume": float(item["volume"]),
                    "atr_14": None,
                    "provider": "eodhd"
                })

    elif provider_name == "finage":
        if "results" in raw_response:
            for item in raw_response["results"]:
                results.append({
                    "timestamp": datetime.strptime(item["datetime"], "%Y-%m-%d %H:%M:%S"),
                    "open": float(item["open"]),
                    "high": float(item["high"]),
                    "low": float(item["low"]),
                    "close": float(item["close"]),
                    "volume": float(item["volume"]),
                    "atr_14": None,  # Assuming Finage doesn't include it by default
                    "provider": "finage"
                })

    return results
