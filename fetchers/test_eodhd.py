# C:\Users\AHMED AL BALUSHI\Montalaq_2\fetchers\test_eodhd.py

import requests
import os
from dotenv import load_dotenv
import pandas as pd

# Load API key
load_dotenv("C:\\Users\\AHMED AL BALUSHI\\Montalaq_2\\.env")
API_KEY = os.getenv("EODHD_API_KEY")

# Read currency pair from Excel
pair_path = "C:\\Users\\AHMED AL BALUSHI\\Montalaq_2\\tests\\currency_pair.xlsx"
df = pd.read_excel(pair_path)
pair = df.iloc[0, 0]  # e.g. EURUSD or EUR/USD

# Normalize to EODHD format: 'EURUSD.FOREX'
symbol = pair.replace("/", "") + ".FOREX"

url = f"https://eodhd.com/api/intraday/{symbol}"
params = {
    "interval": "1m",
    "range": "1h",
    "api_token": API_KEY,
    "fmt": "json"
}

print(f"Requesting data for {symbol} from EODHD...")
response = requests.get(url, params=params)

if response.status_code != 200:
    print("❌ HTTP error:", response.status_code, response.text)
    exit()

try:
    raw = response.json()
except Exception as e:
    print("❌ JSON decoding failed:", str(e))
    print("Raw text:", response.text)
    exit()

if not isinstance(raw, list):
    print("⚠️ No data returned from EODHD or unexpected format.")
    print("Raw response:", raw)
    exit()

print("✅ Received data from EODHD:")

for row in raw[:5]:
    print({
        "timestamp": row.get("datetime"),
        "open": row.get("open"),
        "high": row.get("high"),
        "low": row.get("low"),
        "close": row.get("close"),
        "volume": row.get("volume"),
        "atr_14": None,
        "provider": "eodhd"
    })
