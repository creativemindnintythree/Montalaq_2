# File: C:\Users\AHMED AL BALUSHI\Montalaq_2\trading\rules\stage_13_confirmation.py
"""
Stage 1.3 – Confirmation
Agent 010 – Rule-Based Analysis Engine
"""

from .constants import (
    STAGE_13_WEIGHT,
    RED_FLAG_STRICT_NEEDS_CONFIRM,
    ENABLE_RULE_DEBUG_LOGS
)

def evaluate_stage_13(market: dict, strict: bool = True) -> tuple[bool, dict, bool]:
    """
    Confirm that the identified pattern has follow-through.

    Parameters:
        market (dict): Must contain:
            - pattern (str)
            - confirmation_bars (list[dict]): OHLCV for bars after pattern
            - volume_z (float)
            - trigger_price (float): breakout trigger based on pattern
        strict (bool): If True, must meet strict confirmation conditions.

    Returns:
        passed: bool
        meta: dict
        red_flag: bool
    """
    pattern = market.get("pattern")
    confirmation_bars = market.get("confirmation_bars", [])
    volume_z = market.get("volume_z", 0)
    trigger_price = market.get("trigger_price")

    passed = False
    red_flag = False

    # No pattern → cannot confirm
    if not pattern or pattern == "none":
        return False, {"pattern_confirmed": False, "points_awarded": 0}, red_flag

    # Strict confirmation: close beyond trigger within next 2 bars AND volume_z > 0.5
    if strict:
        for bar in confirmation_bars[:2]:
            if pattern.startswith("bullish") and bar['close'] > trigger_price and volume_z > 0.5:
                passed = True
                break
            if pattern.startswith("bearish") and bar['close'] < trigger_price and volume_z > 0.5:
                passed = True
                break
        if not passed and RED_FLAG_STRICT_NEEDS_CONFIRM:
            red_flag = True

    # Probabilistic confirmation: lighter conditions
    else:
        for bar in confirmation_bars[:3]:
            ema8 = bar.get("ema8")
            if ema8:
                if pattern.startswith("bullish") and bar['close'] > ema8:
                    passed = True
                    break
                if pattern.startswith("bearish") and bar['close'] < ema8:
                    passed = True
                    break

    points = STAGE_13_WEIGHT if passed else 0

    if ENABLE_RULE_DEBUG_LOGS:
        print(f"[Stage 1.3] Pattern={pattern} Strict={strict} Passed={passed} Points={points} RedFlag={red_flag}")

    return passed, {
        "pattern_confirmed": passed,
        "points_awarded": points
    }, red_flag
