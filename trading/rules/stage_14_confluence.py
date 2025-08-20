# File: C:\Users\AHMED AL BALUSHI\Montalaq_2\trading\rules\stage_14_confluence.py
"""
Stage 1.4 – Indicator Confluence
Agent 010 – Rule-Based Analysis Engine
"""

from .constants import (
    STAGE_14_BONUS,
    DEFAULT_CONFLUENCE_STRATEGY,
    RSI_LONG_THRESHOLD,
    RSI_SHORT_THRESHOLD,
    RSI_MIN_DELTA,
    ENABLE_RULE_DEBUG_LOGS
)

def evaluate_stage_14(market: dict, strategy: str = None) -> tuple[bool, dict]:
    """
    Evaluate optional indicator confluence.

    Parameters:
        market (dict): Must contain indicator values required by the strategy.
        strategy (str): Name of strategy to use; defaults to DEFAULT_CONFLUENCE_STRATEGY.

    Returns:
        passed: bool
        meta: dict with confluence details.
    """
    if not strategy:
        strategy = DEFAULT_CONFLUENCE_STRATEGY

    passed = False
    bonus_points = 0
    details = {
        "indicator_confluence": False,
        "confluence_ok": False,
        "confluence_strategy": strategy,
        "points_awarded": 0
    }

    if strategy == "rsi_volume":
        rsi = market.get("rsi14")
        volume_support = market.get("volume_support", False)
        rsi_prev = market.get("rsi14_prev")

        if rsi is not None and rsi_prev is not None:
            rsi_rising = (rsi - rsi_prev) >= RSI_MIN_DELTA
            rsi_falling = (rsi_prev - rsi) >= RSI_MIN_DELTA

            if market.get("direction") == "LONG" and rsi < RSI_LONG_THRESHOLD and rsi_rising and volume_support:
                passed = True
            elif market.get("direction") == "SHORT" and rsi > RSI_SHORT_THRESHOLD and rsi_falling and volume_support:
                passed = True

    elif strategy == "ema_price_sr":
        ema20 = market.get("ema20")
        ema50 = market.get("ema50")
        close = market.get("close")
        pattern_location_sr = market.get("pattern_location_sr", False)

        if market.get("direction") == "LONG" and close > ema20 > ema50 and pattern_location_sr:
            passed = True
        elif market.get("direction") == "SHORT" and close < ema20 < ema50 and pattern_location_sr:
            passed = True

    # Assign bonus if passed
    if passed:
        bonus_points = STAGE_14_BONUS
        details.update({
            "indicator_confluence": True,
            "confluence_ok": True,
            "points_awarded": bonus_points
        })
    else:
        details.update({
            "indicator_confluence": True,
            "confluence_ok": False,
            "points_awarded": 0
        })

    if ENABLE_RULE_DEBUG_LOGS:
        print(f"[Stage 1.4] Strategy={strategy} Passed={passed} Points={bonus_points}")

    return passed, details
