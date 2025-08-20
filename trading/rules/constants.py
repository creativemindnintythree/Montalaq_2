# File: C:\Users\AHMED AL BALUSHI\Montalaq_2\trading\rules\constants.py
"""
Constants for Stage 1.1–1.4 rule weights, thresholds, and execution settings.
Agent 010 – Rule-Based Analysis Engine
"""

# Stage Weights
STAGE_11_WEIGHT = 25
STAGE_12_WEIGHT = 25
STAGE_13_WEIGHT = 25
STAGE_14_BONUS = 25

# Thresholds
MIN_CONFIDENCE_TO_TRADE = 60
INCONCLUSIVE_THRESHOLD = 40

# ATR & Risk:Reward Defaults
ATR_MULTIPLIER_SL = 1.5      # Stop loss distance in ATR multiples
DEFAULT_RR_RATIO = 2.0       # Default Risk:Reward ratio

# Red-Flag Rules
RED_FLAG_NO_PATTERN = True
RED_FLAG_STRICT_NEEDS_CONFIRM = True

# Debug Logging
ENABLE_RULE_DEBUG_LOGS = True

# Pattern List
BULLISH_PATTERNS = ["bullish_engulfing", "hammer"]
BEARISH_PATTERNS = ["bearish_engulfing", "shooting_star"]

# Support/Resistance proximity multiplier
SR_PROXIMITY_ATR_MULTIPLIER = 0.5

# Confluence defaults
DEFAULT_CONFLUENCE_STRATEGY = "rsi_volume"  # default option: "rsi_volume" or "ema_price_sr"
RSI_LONG_THRESHOLD = 50
RSI_SHORT_THRESHOLD = 50
RSI_MIN_DELTA = 2

# Confluence settings dict (optional additional tuning)
default_confluence = {
    "rsi_range": (40, 60),
    "min_volume_z": 0.5,
}
