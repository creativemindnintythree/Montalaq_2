# File: C:\Users\AHMED AL BALUSHI\Montalaq_2\trading\rules\stage_12_patterns.py
"""
Stage 1.2 – Pattern Identification
Agent 010 – Rule-Based Analysis Engine
"""

from .constants import (
    STAGE_12_WEIGHT,
    RED_FLAG_NO_PATTERN,
    SR_PROXIMITY_ATR_MULTIPLIER,
    BULLISH_PATTERNS,
    BEARISH_PATTERNS,
    ENABLE_RULE_DEBUG_LOGS
)

def detect_pattern(candles: list[dict]) -> str:
    """Detect minimal, robust candlestick patterns from the last 2 bars.
    candles: list of dicts with keys: open, high, low, close.
    Returns a lowercase pattern name or 'none'.
    """
    if len(candles) < 2:
        return "none"

    c0, c1 = candles[-1], candles[-2]
    body0 = abs(c0['close'] - c0['open'])
    body1 = abs(c1['close'] - c1['open'])
    range0 = c0['high'] - c0['low']
    range1 = c1['high'] - c1['low']

    # Bullish Engulfing
    if (c0['close'] > c0['open'] and c1['close'] < c1['open'] and
        c0['close'] >= c1['open'] and c0['open'] <= c1['close']):
        return "bullish_engulfing"

    # Bearish Engulfing
    if (c0['close'] < c0['open'] and c1['close'] > c1['open'] and
        c0['close'] <= c1['open'] and c0['open'] >= c1['close']):
        return "bearish_engulfing"

    # Hammer (bullish pin)
    lower_wick = c0['low'] - min(c0['close'], c0['open'])
    upper_wick = c0['high'] - max(c0['close'], c0['open'])
    if lower_wick >= 2 * body0 and c0['close'] > (c0['low'] + range0 * 2/3):
        return "hammer"

    # Shooting Star (bearish pin)
    if upper_wick >= 2 * body0 and c0['close'] < (c0['high'] - range0 * 2/3):
        return "shooting_star"

    return "none"

def evaluate_stage_12(market: dict) -> tuple[bool, dict, bool]:
    """
    Evaluate pattern presence and location at/near S/R.

    Returns:
        passed: bool
        meta: dict with pattern, location flag, points_awarded
        red_flag: bool
    """
    pattern = detect_pattern(market.get("candles", []))
    atr = market.get("atr", 0)
    close = market.get("close")
    key_levels = market.get("key_levels", [])

    # Location at/near SR
    pattern_location_sr = False
    for lvl in key_levels:
        if lvl is not None and abs(close - lvl) <= SR_PROXIMITY_ATR_MULTIPLIER * atr:
            pattern_location_sr = True
            break

    # Scoring
    points = 0
    passed = False
    red_flag = False

    if pattern != "none":
        points += 15  # base for pattern presence
        if pattern_location_sr:
            points += 15
        if points > 0:
            passed = True
    else:
        if RED_FLAG_NO_PATTERN:
            red_flag = True

    if ENABLE_RULE_DEBUG_LOGS:
        print(f"[Stage 1.2] Pattern={pattern} LocSR={pattern_location_sr} Points={points} RedFlag={red_flag}")

    return passed, {
        "candlestick_pattern": pattern,
        "pattern_location_sr": pattern_location_sr,
        "points_awarded": points
    }, red_flag
