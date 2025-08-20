# File: C:\Users\AHMED AL BALUSHI\Montalaq_2\trading\rules\execution.py
"""
Execution Calculations – SL / TP
Agent 010 – Rule-Based Analysis Engine
"""

from .constants import ATR_MULTIPLIER_SL, DEFAULT_RR_RATIO, ENABLE_RULE_DEBUG_LOGS

def calculate_sl_tp(market: dict, direction: str) -> dict:
    """
    Calculate Stop Loss (SL) and Take Profit (TP) using ATR-based method.

    Parameters:
        market (dict): Must contain 'close' and 'atr'.
        direction (str): "LONG" or "SHORT".

    Returns dict:
        {
            "stop_loss": float,
            "take_profit": float,
            "expected_rr": float
        }
    """
    close = market.get("close")
    atr = market.get("atr")

    if close is None or atr is None:
        raise ValueError("Market dict must include 'close' and 'atr' for SL/TP calculation.")

    sl = None
    tp = None

    if direction == "LONG":
        sl = close - (ATR_MULTIPLIER_SL * atr)
        tp = close + ((ATR_MULTIPLIER_SL * atr) * DEFAULT_RR_RATIO)

    elif direction == "SHORT":
        sl = close + (ATR_MULTIPLIER_SL * atr)
        tp = close - ((ATR_MULTIPLIER_SL * atr) * DEFAULT_RR_RATIO)

    expected_rr = DEFAULT_RR_RATIO

    if ENABLE_RULE_DEBUG_LOGS:
        print(f"[Execution] Dir={direction} Close={close} ATR={atr} SL={sl} TP={tp} R:R={expected_rr}")

    return {
        "stop_loss": round(sl, 5) if sl is not None else None,
        "take_profit": round(tp, 5) if tp is not None else None,
        "expected_rr": expected_rr
    }
