# C:\Users\AHMED AL BALUSHI\Montalaq_2\ml_pipeline\prepare_dataset.py

import pandas as pd
import os

# Input and Output paths
input_path = r"C:\Users\AHMED AL BALUSHI\Montalaq_2\outputs\focused_EURUSD.csv"
output_path = r"C:\Users\AHMED AL BALUSHI\Montalaq_2\ml_pipeline\ML_ready_EURUSD.csv"

# Load data
df = pd.read_csv(input_path)

# Drop unused columns
if 'atr_14' in df.columns:
    df.drop(['atr_14', 'provider'], axis=1, inplace=True)

# Convert timestamp to datetime and set index
df['timestamp'] = pd.to_datetime(df['timestamp'])
df.set_index('timestamp', inplace=True)
df = df.sort_index()

# Ensure uniform 1-minute frequency (fill any missing gaps if needed)
df = df.resample('1T').agg({
    'open': 'first',
    'high': 'max',
    'low': 'min',
    'close': 'last',
    'volume': 'sum'
})
df.dropna(inplace=True)

# Feature Engineering
df['pct_change'] = df['close'].pct_change() * 100

# Target: Future return (5-minute ahead % change)
df['target_return_5min'] = df['close'].shift(-5).pct_change(periods=5) * 100

# Optional: Moving averages
df['ma_5'] = df['close'].rolling(window=5).mean()
df['ma_15'] = df['close'].rolling(window=15).mean()

# Drop any resulting NaNs
df.dropna(inplace=True)

# Export to ML-ready CSV
os.makedirs(os.path.dirname(output_path), exist_ok=True)
df.to_csv(output_path)

print(f"✅ ML-ready dataset saved to {output_path} with {len(df)} rows")
