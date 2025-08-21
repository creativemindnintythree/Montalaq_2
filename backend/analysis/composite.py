from django.apps import apps

def _ml_weight_default() -> float:
    # Try MlPreference override (key="ml_weight"), else 0.30
    MlPreference = apps.get_model("backend", "MlPreference")
    try:
        row = MlPreference.objects.filter(key="ml_weight").first()
        return float(row.float_value) if row else 0.30
    except Exception:
        return 0.30

def blend(rule_score: int | float, ml_score: int | float | None) -> int:
    if ml_score is None:
        return int(round(rule_score))
    w = _ml_weight_default()
    return int(round(rule_score * (1 - w) + ml_score * w))
