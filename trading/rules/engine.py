# File: C:\Users\AHMED AL BALUSHI\Montalaq_2\trading\rules\engine.py
"""
Rule Engine – Agent 010 (Stages 1.1–1.4)
"""

from .constants import (
    MIN_CONFIDENCE_TO_TRADE,
    INCONCLUSIVE_THRESHOLD,
    ENABLE_RULE_DEBUG_LOGS
)
from .stage_11_context import evaluate_stage_11
from .stage_12_patterns import evaluate_stage_12
from .stage_13_confirmation import evaluate_stage_13
from .stage_14_confluence import evaluate_stage_14

def run_rule_engine(market: dict, strict_confirmation: bool = True) -> dict:
    """
    Run Stages 1.1–1.4 sequentially, compute score, and decide trade.

    Parameters:
        market (dict): The market dict from ingestion/pipeline agents.
        strict_confirmation (bool): Whether to require strict confirmation.

    Returns dict with:
        final_decision (str)
        confidence_score (int)
        stage_11, stage_12, stage_13, stage_14 (dicts with results)
        red_flag (bool)
    """

    total_points = 0
    red_flag = False
    direction = None

    # Stage 1.1 – Context
    s11_pass, s11_meta = evaluate_stage_11(market)
    total_points += s11_meta["points_awarded"]

    # Stage 1.2 – Patterns
    s12_pass, s12_meta, s12_red = evaluate_stage_12(market)
    total_points += s12_meta["points_awarded"]
    if s12_red:
        red_flag = True
    pattern = s12_meta.get("candlestick_pattern")
    if pattern in ("bullish_engulfing", "hammer", "morning_star"):
        direction = "LONG"
    elif pattern in ("bearish_engulfing", "shooting_star", "evening_star"):
        direction = "SHORT"
    market["pattern"] = pattern

    # Stage 1.3 – Confirmation
    market["pattern"] = pattern
    s13_pass, s13_meta, s13_red = evaluate_stage_13(market, strict=strict_confirmation)
    total_points += s13_meta["points_awarded"]
    if s13_red:
        red_flag = True

    # Stage 1.4 – Confluence
    market["direction"] = direction
    s14_pass, s14_meta = evaluate_stage_14(market)
    total_points += s14_meta["points_awarded"]
    if s14_meta["indicator_confluence"] and not s14_meta["confluence_ok"]:
        red_flag = True

    # Compute confidence
    confidence_score = min(int(total_points), 100)

    # Decision logic
    if red_flag or confidence_score < INCONCLUSIVE_THRESHOLD:
        final_decision = "NO_TRADE"
    elif confidence_score >= MIN_CONFIDENCE_TO_TRADE:
        final_decision = direction if direction else "NO_TRADE"
    else:
        final_decision = direction if direction else "NO_TRADE"

    if ENABLE_RULE_DEBUG_LOGS:
        print(f"[Engine] Score={confidence_score} RedFlag={red_flag} Decision={final_decision}")

    return {
        "final_decision": final_decision,
        "confidence_score": confidence_score,
        "stage_11": s11_meta,
        "stage_12": s12_meta,
        "stage_13": s13_meta,
        "stage_14": s14_meta,
        "red_flag": red_flag
    }
