# File: C:\Users\AHMED AL BALUSHI\Montalaq_2\celery_tasks\run_rule_engine.py
"""
Celery Task – Run Rule Engine (Agent 010)
"""

from celery import shared_task
from django.utils import timezone
from backend.models import MarketDataFeatures, TradeAnalysis
from trading.rules.engine import run_rule_engine
from trading.rules.execution import calculate_sl_tp

@shared_task
def run_rule_engine_task(symbol: str, timeframe: str = "1m"):
    """
    Run the rule engine for the latest MarketDataFeatures entry of a symbol/timeframe.
    Saves output to TradeAnalysis.
    """
    try:
        # 1. Fetch latest MarketDataFeatures for the symbol
        mdf = (MarketDataFeatures.objects
               .filter(market_data__symbol=symbol)
               .order_by('-market_data__timestamp')
               .select_related('market_data')
               .first())
        
        if not mdf:
            return f"No MarketDataFeatures found for {symbol}"

        # Build market dict for engine.py
        market = {
            "open": mdf.market_data.open,
            "high": mdf.market_data.high,
            "low": mdf.market_data.low,
            "close": mdf.market_data.close,
            "volume": mdf.market_data.volume,
            "atr": mdf.atr_14,
            "ema8": mdf.ema_8,
            "ema20": mdf.ema_20,
            "ema50": mdf.ema_50,
            "rsi14": mdf.rsi_14,
            "volume_z": mdf.volume_zscore,
            # Placeholders for now – upstream agents should provide
            "key_levels": [],
            "candles": [],
            "confirmation_bars": []
        }

        # 2. Pass to rule engine
        engine_results = run_rule_engine(market, strict_confirmation=True)

        # 3. Calculate SL/TP
        sl_tp = calculate_sl_tp(market, engine_results.get("final_decision"))

        # 4. Save results to TradeAnalysis via ORM
        ta = TradeAnalysis.objects.create(
            market_data_feature=mdf,
            rule_confidence_score=engine_results.get("confidence_score"),
            final_decision=engine_results.get("final_decision"),
            volume_support=engine_results.get("stage_11", {}).get("volume_support", False),
            proximity_to_sr=engine_results.get("stage_11", {}).get("proximity_to_sr", False),
            candlestick_pattern=engine_results.get("stage_12", {}).get("candlestick_pattern"),
            pattern_location_sr=engine_results.get("stage_12", {}).get("pattern_location_sr", False),
            pattern_confirmed=engine_results.get("stage_13", {}).get("pattern_confirmed", False),
            indicator_confluence=engine_results.get("stage_14", {}).get("indicator_confluence", False),
            confluence_ok=engine_results.get("stage_14", {}).get("confluence_ok", False),
            entry_price=market.get("close"),
            stop_loss=sl_tp.get("stop_loss"),
            take_profit=sl_tp.get("take_profit")
        )

        return f"Rule Engine completed for {symbol} at {timezone.now()} – TradeAnalysis ID {ta.id}"

    except Exception as e:
        return f"Error running rule engine: {str(e)}"
