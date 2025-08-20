# C:\Users\AHMED AL BALUSHI\Montalaq_2\fetchers\test_finnhub.py

import requests
import os
from dotenv import load_dotenv
import pandas as pd
from datetime import datetime

# Load API key from .env
load_dotenv("C:\\Users\\AHMED AL BALUSHI\\Montalaq_2\\.env")
API_KEY = os.getenv("FINNHUB_API_KEY")

# Read currency pair from Excel
pair_path = "C:\\Users\\AHMED AL BALUSHI\\Montalaq_2\\tests\\currency_pair.xlsx"
df = pd.read_excel(pair_path)
pair = df.iloc[0, 0]  # Assume first cell is the pair name (e.g., EURUSD)

# Use plain symbol format (e.g., 'EURUSD')
symbol = pair

# API Endpoint
url = "https://finnhub.io/api/v1/forex/candle"
params = {
    "symbol": symbol,
    "resolution": "1",  # 1-minute candles
    "count": 50,
    "token": API_KEY
}

print(f"Requesting data for {symbol} from Finnhub...")
response = requests.get(url, params=params)

if response.status_code != 200:
    print("❌ Failed to fetch from Finnhub:", response.status_code, response.text)
    exit()

raw = response.json()

if "t" not in raw or not raw["t"]:
    print("⚠️ No candle data returned.")
    exit()

print("✅ Received OHLCV data from Finnhub:")

# Show sample of parsed candles
for i in range(min(5, len(raw["t"]))):
    ts = datetime.utcfromtimestamp(raw["t"][i])
    print({
        "timestamp": ts,
        "open": raw["o"][i],
        "high": raw["h"][i],
        "low": raw["l"][i],
        "close": raw["c"][i],
        "volume": raw["v"][i],
        "atr_14": None,  # Not included in Finnhub default response
        "provider": "finnhub"
    })
