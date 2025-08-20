import websocket
import threading
import json
import time
import os
import pandas as pd
from dotenv import load_dotenv
from datetime import datetime, timezone
import uuid

# Load env vars
load_dotenv(r"C:\Users\AHMED AL BALUSHI\Montalaq_2\.env")
API_KEY = os.getenv("ALLTICK_API_KEY")
BACKUP_API_KEY = os.getenv("ALLTICK_API_KEY_BACKUP")

# Get symbol
symbol = pd.read_excel(r"C:\Users\AHMED AL BALUSHI\Montalaq_2\tests\currency_pair.xlsx").iloc[0, 0].replace("/", "")
WSS_URL_TEMPLATE = "wss://quote.alltick.io/quote-b-ws-api?token={key}"

# Data storage
agg = {}
out_path = rf"C:\Users\AHMED AL BALUSHI\Montalaq_2\outputs\focused_{symbol}.csv"

_fetched_any_data = False
_rate_limit_detected = False
heartbeat_interval = 25  # seconds
last_tick_time = time.time()

def update_blob(timestamp_ms, price, size=None):
    dt = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
    minute = dt.strftime("%Y-%m-%d %H:%M")
    price = float(price)
    r = agg.setdefault(minute, {"open": price, "high": price, "low": price, "close": price, "volume": 0.0})
    r["high"] = max(r["high"], price)
    r["low"] = min(r["low"], price)
    r["close"] = price
    if size:
        r["volume"] += float(size)

def append_to_csv(timestamp, o, h, l, c, v):
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    df = pd.DataFrame([{ "timestamp": timestamp, "open": o, "high": h, "low": l, "close": c, "volume": v, "atr_14": None, "provider": "alltick" }])
    header = not os.path.exists(out_path)
    df.to_csv(out_path, mode='a', header=header, index=False)
    print(f"📅 Appended row for {timestamp} → {out_path}")

def heartbeat(ws):
    global last_tick_time
    while True:
        time.sleep(heartbeat_interval)
        try:
            print("💓 Sending heartbeat ping")
            ws.send(json.dumps({"cmd_id": 0, "action": "ping"}))
            # Check idle time
            idle_seconds = time.time() - last_tick_time
            if idle_seconds > heartbeat_interval:
                print(f"ℹ️ No ticks in {int(idle_seconds)} seconds — still connected")
        except Exception as e:
            print("⚠️ Heartbeat failed:", e)
            return

def on_open(ws):
    print(f"🟢 Opened WS — subscribing to {symbol}")
    sub = {
        "cmd_id": 22004,
        "trace": str(uuid.uuid4()),
        "data": {"symbol_list": [{"code": symbol}]}
    }
    ws.send(json.dumps(sub))
    threading.Thread(target=heartbeat, args=(ws,), daemon=True).start()

def on_message(ws, msg):
    global _fetched_any_data, last_tick_time
    print("📨 Raw message:", msg)  # Debug log
    try:
        data = json.loads(msg)
    except json.JSONDecodeError:
        print("⚠️ Invalid JSON:", msg)
        return

    if data.get("cmd_id") == 22005:
        print("🗕️ Subscribed (cmd_id=22005)")
        return

    if data.get("cmd_id") == 22998 and "data" in data:
        tick = data["data"]
        timestamp_ms = int(tick.get("tick_time", 0))
        price = tick.get("price")
        volume = tick.get("volume")
        if timestamp_ms and price is not None:
            _fetched_any_data = True
            last_tick_time = time.time()
            update_blob(timestamp_ms, price, volume)
            dt = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
            minute = dt.strftime("%Y-%m-%d %H:%M")
            row = agg[minute]
            append_to_csv(minute, row["open"], row["high"], row["low"], row["close"], row["volume"])
            print(f"💡 Tick @{timestamp_ms}: price={price}, volume={volume}")
        return

    print("📥 Unhandled cmd:", data.get("cmd_id"), "full:", data)

def on_ping(ws, message):
    print("📡 Received server ping — sending pong")
    ws.send(json.dumps({"action": "pong"}))

def on_error(ws, e):
    global _rate_limit_detected
    print("❌ WS Error:", e)
    if "429" in str(e):
        print("⚠️ Rate limit detected — switching to backup API key if available.")
        _rate_limit_detected = True

def on_close(ws, code, reason):
    print(f"🔌 WS Closed — Code: {code}, Reason: {reason}")
    print("🔄 Attempting immediate reconnect...")
    time.sleep(3)
    connect_ws(API_KEY)

def attempt_fetch(api_key):
    global _fetched_any_data
    _fetched_any_data = False

    ws = websocket.WebSocketApp(
        WSS_URL_TEMPLATE.format(key=api_key),
        on_open=on_open,
        on_message=on_message,
        on_ping=on_ping,
        on_error=on_error,
        on_close=on_close
    )

    ws.run_forever(ping_interval=None, ping_timeout=None)
    return _fetched_any_data

def connect_ws(api_key):
    try:
        attempt_fetch(api_key)
    except Exception as e:
        print("❌ Fatal error in WS connection:", e)

def fetch_alltick_data():
    connect_ws(API_KEY)
    if _rate_limit_detected and BACKUP_API_KEY:
        print("🔁 Trying with backup API key...")
        connect_ws(BACKUP_API_KEY)

if __name__ == "__main__":
    fetch_alltick_data()
