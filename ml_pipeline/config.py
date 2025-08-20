# ml_pipeline/config.py

"""
Configuration constants for ML integration in Montalaq_2.
These defaults are global until Agency 014 user preferences are implemented.
"""

from backend.models import MlPreference

# ML weight and gating threshold (global defaults until Agency 014 user prefs)
DEFAULT_ML_WEIGHT: float = 0.30
MIN_RULE_CONF_FOR_ML: float = 40.0

# Canonical labels
SIGNAL_LONG = "LONG"
SIGNAL_SHORT = "SHORT"
SIGNAL_NO_TRADE = "NO_TRADE"


def get_ml_weight() -> float:
    """
    Fetch the ML weight from MlPreference if available,
    otherwise return the static DEFAULT_ML_WEIGHT.
    """
    try:
        pref = MlPreference.objects.filter(key="ml_weight").first()
        if pref and pref.float_value is not None:
            return float(pref.float_value)
    except Exception:
        # Fallback if DB not ready or query fails
        pass
    return DEFAULT_ML_WEIGHT
