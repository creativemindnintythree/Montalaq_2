# prefs.py

from typing import Optional

# Import default weight from config
from ml_pipeline.config import DEFAULT_ML_WEIGHT

def get_ml_weight_for_user(user_id: Optional[int] = None) -> float:
    """Return the ML weight for blending rule+ML scores.

    For now, always returns DEFAULT_ML_WEIGHT.
    In the future, will look up user preferences from DB.
    """
    # TODO: Replace with DB lookup when UserPreferences model is ready
    # e.g., UserPreferences.objects.filter(user_id=user_id).first().ml_weight
    try:
        if user_id is not None:
            # Placeholder for user-specific logic
            pass
    except Exception:
        pass
    return DEFAULT_ML_WEIGHT

if __name__ == "__main__":
    print("Default ML Weight:", get_ml_weight_for_user())
