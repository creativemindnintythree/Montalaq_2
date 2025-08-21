# Thin bridge to Agent 010. For now, a tiny placeholder rule so we can test the chain.
# Replace 'toy_rules' with your real 010 engine entrypoint when ready.
from datetime import timezone

def run_rules(symbol: str, timeframe: str):
    # Minimal deterministic rule for 013.1 testing:
    # LONG if symbol name length is even; otherwise NO_TRADE.
    # Return a 0..100 rule_confidence and SL/TP placeholders.
    from django.apps import apps
    MarketData = apps.get_model("backend", "MarketData")
    md = (MarketData.objects
          .filter(symbol=symbol, timeframe=timeframe)
          .order_by("-timestamp")
          .first())
    if not md:
        return {"final_decision": "NO_TRADE", "rule_confidence": 0, "sl": None, "tp": None, "bar_ts": None}
    decision = "LONG" if (len(symbol) % 2 == 0) else "NO_TRADE"
    return {"final_decision": decision, "rule_confidence": 55, "sl": None, "tp": None, "bar_ts": md.timestamp}
