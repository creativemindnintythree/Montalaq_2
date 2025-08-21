# Thin bridge to Agent 011. Minimal stub for 013.1 testing.
def run_ml(symbol: str, timeframe: str, bar_ts) -> int:
    # Return a 'confidence' 0..100; simple fixed 60 for now.
    return 60
