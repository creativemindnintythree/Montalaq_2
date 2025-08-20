from celery import shared_task
from django.utils import timezone
from ml_pipeline.data_preprocessor import process_data  # FIXED: use function instead of missing class
from backend.models import MarketData, MarketDataFeatures  # FIXED: corrected import path
import pandas as pd
import logging

logger = logging.getLogger(__name__)

def save_features_to_db(processed_df: pd.DataFrame):
    saved_count = 0
    for _, row in processed_df.iterrows():
        try:
            market_data = MarketData.objects.get(timestamp=row['timestamp'], symbol=row['symbol'])
            MarketDataFeatures.objects.update_or_create(
                market_data=market_data,
                defaults={
                    'atr_14': row.get('atr_14'),
                    'ema_8': row.get('ema_8'),
                    'ema_20': row.get('ema_20'),
                    'ema_50': row.get('ema_50'),
                    'rsi_14': row.get('rsi_14'),
                    'bb_bbm': row.get('bb_bbm'),
                    'bb_bbh': row.get('bb_bbh'),
                    'bb_bbl': row.get('bb_bbl'),
                    'bb_bandwidth': row.get('bb_bandwidth'),
                    'vwap': row.get('vwap'),
                    'vwap_dist': row.get('vwap_dist'),
                    'volume_zscore': row.get('volume_zscore'),
                    'range_atr_ratio': row.get('range_atr_ratio'),
                    'ema_bull_cross': bool(row.get('ema_bull_cross')),
                    'ema_bear_cross': bool(row.get('ema_bear_cross')),
                    'rsi_overbought': bool(row.get('rsi_overbought')),
                    'rsi_oversold': bool(row.get('rsi_oversold')),
                    'bb_squeeze': bool(row.get('bb_squeeze')),
                }
            )
            saved_count += 1
        except MarketData.DoesNotExist:
            logger.warning(f"No MarketData entry found for timestamp={row['timestamp']} and symbol={row['symbol']}")
            continue
    logger.info(f"Saved/Updated features for {saved_count} records.")

@shared_task
def run_feature_engineering(symbol: str):
    start_time = timezone.now()
    logger.info(f"Starting feature engineering for {symbol} at {start_time}")

    try:
        raw_qs = MarketData.objects.filter(symbol=symbol).order_by('timestamp')
        if not raw_qs.exists():
            logger.warning(f"No data for symbol {symbol}")
            return f"⚠️ No data for symbol {symbol}"

        df = pd.DataFrame(list(raw_qs.values()))

        # Process features using function
        processed_df = process_data(df)

        # Ensure symbol column exists in processed_df
        if 'symbol' not in processed_df.columns:
            processed_df['symbol'] = symbol

        save_features_to_db(processed_df)

        duration = (timezone.now() - start_time).total_seconds()
        logger.info(f"✅ Features generated for {symbol} in {duration:.2f}s")
        return f"✅ Features generated for {symbol} in {duration:.2f}s"

    except Exception as e:
        logger.exception(f"❌ Error during feature engineering for {symbol}: {e}")
        return f"❌ Error during feature engineering for {symbol}: {str(e)}"
