import pandas as pd
import numpy as np
from ta.volatility import AverageTrueRange, BollingerBands
from ta.trend import EMAIndicator
from ta.momentum import RSIIndicator

def process_data(df: pd.DataFrame) -> pd.DataFrame:
    """Full preprocessing pipeline for EURUSD data."""
    # Ensure correct dtypes
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    numeric_cols = ['open', 'high', 'low', 'close', 'volume']
    df[numeric_cols] = df[numeric_cols].apply(pd.to_numeric, errors='coerce')

    # Drop rows with missing OHLCV
    df.dropna(subset=numeric_cols, inplace=True)

    # Deduplicate by timestamp (aggregate OHLCV)
    df = df.groupby('timestamp').agg({
        'open': 'first',
        'high': 'max',
        'low': 'min',
        'close': 'last',
        'volume': 'sum',
        'provider': 'first'
    }).reset_index()

    # ATR(14)
    atr_indicator = AverageTrueRange(high=df['high'], low=df['low'], close=df['close'], window=14)
    df['atr_14'] = atr_indicator.average_true_range()

    # EMA
    df['ema_8'] = EMAIndicator(df['close'], window=8).ema_indicator()
    df['ema_20'] = EMAIndicator(df['close'], window=20).ema_indicator()
    df['ema_50'] = EMAIndicator(df['close'], window=50).ema_indicator()

    # RSI
    df['rsi_14'] = RSIIndicator(df['close'], window=14).rsi()

    # Bollinger Bands
    bb = BollingerBands(df['close'], window=20, window_dev=2)
    df['bb_bbm'] = bb.bollinger_mavg()
    df['bb_bbh'] = bb.bollinger_hband()
    df['bb_bbl'] = bb.bollinger_lband()
    df['bb_bandwidth'] = (df['bb_bbh'] - df['bb_bbl']) / df['bb_bbm']

    # VWAP distance
    cumulative_vp = (df['close'] * df['volume']).cumsum()
    cumulative_vol = df['volume'].cumsum()
    df['vwap'] = cumulative_vp / cumulative_vol
    df['vwap_dist'] = (df['close'] - df['vwap']) / df['vwap']

    # Volume Z-score
    df['volume_zscore'] = (df['volume'] - df['volume'].rolling(20).mean()) / df['volume'].rolling(20).std()

    # Range/ATR ratio
    df['range_atr_ratio'] = ((df['high'] - df['low']) / df['atr_14']).replace([np.inf, -np.inf], np.nan)

    # EMA crossover flags
    df['ema_bull_cross'] = (df['ema_8'] > df['ema_20']).astype(int)
    df['ema_bear_cross'] = (df['ema_8'] < df['ema_20']).astype(int)

    # RSI extremes
    df['rsi_overbought'] = (df['rsi_14'] > 70).astype(int)
    df['rsi_oversold'] = (df['rsi_14'] < 30).astype(int)

    # Bollinger squeeze
    df['bb_squeeze'] = (df['bb_bandwidth'] < df['bb_bandwidth'].rolling(20).quantile(0.2)).astype(int)

    # Drop NaNs from indicator calculations
    df.dropna(inplace=True)

    return df
