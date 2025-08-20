# C:\Users\AHMED AL BALUSHI\Montalaq_2\fetchers\test_twelvedata.py

import requests
import os
from dotenv import load_dotenv
import pandas as pd

# Load API key
load_dotenv("C:\\Users\\AHMED AL BALUSHI\\Montalaq_2\\.env")
API_KEY = os.getenv("TWELVEDATA_API_KEY")

# Read pair
pair_path = "C:\\Users\\AHMED AL BALUSHI\\Montalaq_2\\tests\\currency_pair.xlsx"
df = pd.read_excel(pair_path)
pair = df.iloc[0, 0]  # e.g. EURUSD or EUR/USD

# Normalize format for TwelveData
symbol = pair if "/" in pair else f"{pair[:3]}/{pair[3:]}"

url = "https://api.twelvedata.com/time_series"
params = {
    "symbol": symbol,
    "interval": "1min",
    "outputsize": 50,
    "indicators": "atr",
    "apikey": API_KEY
}

print(f"Requesting data for {symbol} from TwelveData...")
response = requests.get(url, params=params)

if response.status_code != 200:
    print("❌ HTTP error:", response.status_code, response.text)
    exit()

raw = response.json()

if "values" not in raw:
    print("⚠️ No data returned from TwelveData.")
    print("Raw response:", raw)
    exit()

print("✅ Received data from TwelveData:")

for row in raw["values"][:5]:
    print({
        "timestamp": row.get("datetime"),
        "open": row.get("open"),
        "high": row.get("high"),
        "low": row.get("low"),
        "close": row.get("close"),
        "volume": row.get("volume"),
        "atr_14": row.get("atr"),
        "provider": "twelvedata"
    })
