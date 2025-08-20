from celery import shared_task
from django.utils import timezone
from backend_app.models import MarketDataFeatures, TradeAnalysis
from ml_pipeline.ml_model import MLModel
from ml_pipeline.execution_logic import ExecutionLogic
import pandas as pd

@shared_task
def run_ml_on_new_data(symbol: str):
    # Pull recent features without predictions
    features_qs = MarketDataFeatures.objects.filter(
        market_data__symbol=symbol,
        trade_analysis__isnull=True
    ).order_by('market_data__timestamp')

    if not features_qs.exists():
        return f"No new feature data for symbol {symbol}"

    df = pd.DataFrame(list(features_qs.values()))
    feature_cols = [col for col in df.columns if col not in ['id', 'market_data_id']]

    # Run ML predictions
    ml = MLModel()
    pred_labels, pred_probs = ml.predict(df[feature_cols])

    # Process each prediction
    for i, row in enumerate(features_qs):
        label = pred_labels[i]
        probs = pred_probs[i]
        signal_map = {0: 'LONG', 1: 'SHORT', 2: 'NO_TRADE'}
        ml_signal = signal_map[label]

        # Generate execution plan (entry, SL, TP)
        exec_plan = ExecutionLogic.generate(
            entry_price=row.market_data.close,
            atr=row.atr_14,
            signal=ml_signal
        )

        TradeAnalysis.objects.create(
            market_data_feature=row,
            ml_signal=ml_signal,
            ml_prob_long=probs[0],
            ml_prob_short=probs[1],
            ml_prob_no_trade=probs[2],
            ml_expected_rr=exec_plan['expected_rr'],
            ml_model_version='v1',  # can be dynamically set
            entry_price=exec_plan['entry_price'],
            stop_loss=exec_plan['stop_loss'],
            take_profit=exec_plan['take_profit']
        )

    return f"✅ ML predictions + execution plans generated for {symbol} at {timezone.now()}"
