import pandas as pd
import pytz

"""
TEMPORARY BRIDGE – REMOVE WHEN OFFICIAL INGESTION READY (Agents 012/013)

Purpose:
    Loads OHLCV bars from focused_EURUSD.csv into the canonical market dict
    format expected by Agent 010's rules engine.

Usage:
    from trading.data_adapters.csv_marketdata_bridge import load_latest_market_data
    market_dict = load_latest_market_data("C:/Users/AHMED AL BALUSHI/Montalaq_2/outputs/focused_EURUSD.csv")

Note:
    - For testing only, not production.
    - CSV must contain at least: timestamp, open, high, low, close, volume.
"""

def load_latest_market_data(csv_path: str) -> dict:
    # Load CSV into DataFrame
    df = pd.read_csv(csv_path)

    if df.empty:
        raise ValueError("CSV file is empty — no market data available.")

    # Ensure timestamp is parsed and timezone-aware (UTC)
    if not pd.api.types.is_datetime64_any_dtype(df["timestamp"]):
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    else:
        # Localize naive datetimes to UTC
        if df["timestamp"].dt.tz is None:
            df["timestamp"] = df["timestamp"].dt.tz_localize(pytz.UTC)

    # Calculate ATR(14) if not present
    if "atr" not in df.columns:
        high_low = df["high"] - df["low"]
        high_close_prev = (df["high"] - df["close"].shift()).abs()
        low_close_prev = (df["low"] - df["close"].shift()).abs()
        tr = pd.concat([high_low, high_close_prev, low_close_prev], axis=1).max(axis=1)
        df["atr"] = tr.rolling(window=14, min_periods=1).mean()

    # Assume latest bar is last row
    latest = df.iloc[-1]

    # Canonical mapping
    market = {
        "timestamp": latest["timestamp"],
        "open": float(latest["open"]),
        "high": float(latest["high"]),
        "low": float(latest["low"]),
        "close": float(latest["close"]),
        "volume": float(latest["volume"]),
        "atr": float(latest["atr"]),
    }

    return market
