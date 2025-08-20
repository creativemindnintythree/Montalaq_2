# ml_pipeline/config.py

"""
Configuration constants for ML integration in Montalaq_2.
These defaults are global until Agency 014 user preferences are implemented.
"""

# ML weight and gating threshold (global defaults until Agency 014 user prefs)
DEFAULT_ML_WEIGHT: float = 0.30
MIN_RULE_CONF_FOR_ML: float = 40.0

# Canonical labels
SIGNAL_LONG = "LONG"
SIGNAL_SHORT = "SHORT"
SIGNAL_NO_TRADE = "NO_TRADE"
