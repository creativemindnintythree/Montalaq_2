"""
Stage 1.1 – Price/Volume Context
Agent 010 – Rule-Based Analysis Engine
"""

from .constants import (
    STAGE_11_WEIGHT,
    SR_PROXIMITY_ATR_MULTIPLIER,
    ENABLE_RULE_DEBUG_LOGS
)

def evaluate_stage_11(market: dict) -> tuple[bool, dict]:
    """
    Evaluate price & volume context conditions.

    Parameters:
        market (dict): Must contain:
            - close (float)
            - volume_z (float)  # Z-score of volume
            - atr (float)
            - key_levels (list[float])  # Support/resistance prices
            - last_pdh (float)
            - last_pdl (float)

    Returns:
        (passed: bool, meta: dict)
        meta includes:
            - volume_support (bool)
            - proximity_to_sr (bool)
            - points_awarded (int)
    """
    close = market.get("close")
    volume_z = market.get("volume_z", 0)
    atr = market.get("atr", 0)
    key_levels = market.get("key_levels", [])
    last_pdh = market.get("last_pdh")
    last_pdl = market.get("last_pdl")

    # 1) Volume support check (Z-score > 1.0 as example threshold)
    volume_support = volume_z > 1.0

    # 2) Proximity to support/resistance
    proximity_to_sr = False
    for lvl in key_levels + [last_pdh, last_pdl]:
        if lvl is not None and abs(close - lvl) <= SR_PROXIMITY_ATR_MULTIPLIER * atr:
            proximity_to_sr = True
            break

    # Stage pass condition
    passed = volume_support and proximity_to_sr
    points = STAGE_11_WEIGHT if passed else 0

    if ENABLE_RULE_DEBUG_LOGS:
        print(f"[Stage 1.1] Close={close} VolZ={volume_z} ATR={atr} "
              f"VolSupport={volume_support} NearSR={proximity_to_sr} "
              f"Points={points}")

    return passed, {
        "volume_support": volume_support,
        "proximity_to_sr": proximity_to_sr,
        "points_awarded": points
    }
