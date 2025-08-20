# File: C:\Users\AHMED AL BALUSHI\Montalaq_2\pipeline_tester.py
"""
Pipeline Tester – End-to-End Check for Agent 010 (TEMP CSV BRIDGE MODE)
Runs CSV bridge → (create minimal MarketData/Features) → rules → DB persistence
using latest data from focused_EURUSD.csv.

Note:
  • We create a lightweight MarketData + MarketDataFeatures row so TradeAnalysis.FK is NOT NULL.
  • This keeps DB schema unchanged and respects Agent 009's boundary (no model edits).
"""

import os
import django
from django.utils import timezone

# Setup Django environment
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "montalaq_project.settings")
django.setup()

from backend.models import MarketData, MarketDataFeatures, TradeAnalysis
from trading.data_adapters.csv_marketdata_bridge import load_latest_market_data
from trading.rules.engine import run_rule_engine
from trading.rules.execution import calculate_sl_tp

CSV_PATH = r"C:\\Users\\AHMED AL BALUSHI\\Montalaq_2\\outputs\\focused_EURUSD.csv"
SYMBOL = "EUR/USD"
PROVIDER = "CSV_BRIDGE"

def ensure_mdf_for_csv_bar(market: dict) -> MarketDataFeatures:
    """Create (or reuse) a MarketData + MarketDataFeatures row for the CSV bar."""
    ts = market.get("timestamp")
    md, _ = MarketData.objects.get_or_create(
        timestamp=ts,
        symbol=SYMBOL,
        defaults={
            "open": market.get("open"),
            "high": market.get("high"),
            "low": market.get("low"),
            "close": market.get("close"),
            "volume": market.get("volume", 0.0),
            "provider": PROVIDER,
        },
    )

    # Create or update features
    mdf, created = MarketDataFeatures.objects.get_or_create(
        market_data=md,
        defaults={
            "atr_14": market.get("atr"),
            "ema_8": None,
            "ema_20": None,
            "ema_50": None,
            "rsi_14": None,
            "volume_zscore": None,
        },
    )
    if not created:
        changed = False
        new_atr = market.get("atr")
        if new_atr is not None and mdf.atr_14 != new_atr:
            mdf.atr_14 = new_atr
            changed = True
        if changed:
            mdf.save(update_fields=["atr_14"])
    return mdf

def run_pipeline_test_csv(symbol: str):
    print(f"[Pipeline Tester] Starting CSV-bridge test for {symbol} at {timezone.now()}")

    market = load_latest_market_data(CSV_PATH)
    print(f"[Pipeline Tester] Loaded latest market data: {market}")

    mdf = ensure_mdf_for_csv_bar(market)

    results = run_rule_engine(market)

    decision = results.get("final_decision")
    confidence = results.get("confidence_score")

    stage_11 = results.get("stage_11", {})
    stage_12 = results.get("stage_12", {})
    stage_13 = results.get("stage_13", {})
    stage_14 = results.get("stage_14", {})

    sltp = calculate_sl_tp(market, decision)

    analysis = TradeAnalysis.objects.create(
        market_data_feature=mdf,
        rule_confidence_score=confidence,
        final_decision=decision,
        volume_support=stage_11.get("volume_support"),
        proximity_to_sr=stage_11.get("proximity_to_sr"),
        candlestick_pattern=stage_12.get("candlestick_pattern"),
        pattern_location_sr=stage_12.get("pattern_location_sr"),
        pattern_confirmed=stage_13.get("pattern_confirmed"),
        indicator_confluence=stage_14.get("indicator_confluence"),
        confluence_ok=stage_14.get("confluence_ok"),
        entry_price=market.get("close"),
        stop_loss=sltp.get("stop_loss"),
        take_profit=sltp.get("take_profit"),
    )

    print("[Pipeline Tester] ✅ TradeAnalysis entry created (CSV mode):")
    print(f"  ID: {analysis.id}")
    print(f"  Final Decision: {analysis.final_decision}")
    print(f"  Rule Confidence: {analysis.rule_confidence_score}")
    print(f"  SL: {analysis.stop_loss}")
    print(f"  TP: {analysis.take_profit}")

if __name__ == "__main__":
    run_pipeline_test_csv(symbol=SYMBOL)
