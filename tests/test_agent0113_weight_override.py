import pytest
from django.utils import timezone

from backend.models import MarketData, MarketDataFeatures, TradeAnalysis, MlPreference
from ml_pipeline import config as ml_cfg
import celery_tasks.run_ml_on_new_data as runner


@pytest.mark.django_db
def _make_ta(symbol="EURUSD", rc=60, decision=None):
    md = MarketData.objects.create(
        timestamp=timezone.now(),
        symbol=symbol,
        open=1.0, high=1.0, low=1.0, close=1.0, volume=1.0, provider="test",
    )
    mdf = MarketDataFeatures.objects.create(market_data=md)
    ta = TradeAnalysis.objects.create(
        market_data_feature=mdf,
        rule_confidence=rc,
        final_decision=decision or ml_cfg.SIGNAL_LONG,
    )
    return ta


# --- Helpers to control the ML model + features for deterministic math ----
class _ModelFixedLongProb:
    """Minimal model that returns a fixed LONG prob (with 3-class output)."""
    def __init__(self, p_long=0.8):
        self._probs = [p_long, 1.0 - p_long, 0.0]
        self.n_features_in_ = 4

    def predict_proba(self, X):
        # shape (1, 3)
        return [self._probs]


def _patch_model(monkeypatch, model):
    from ml_pipeline import ml_model
    monkeypatch.setattr(ml_model, "get", lambda: model, raising=True)
    monkeypatch.setattr(ml_model, "get_version", lambda: "vX", raising=True)
    monkeypatch.setattr(ml_model, "get_hash_prefix", lambda: "cafebabe", raising=True)


def _patch_zero_vectors(monkeypatch, n=4):
    # Force vector builders to return a zero vector (size n)
    monkeypatch.setattr(runner, "to_vector_for_ta", lambda ta: [0.0]*n, raising=True)
    monkeypatch.setattr(runner, "to_vector_by_feature_names", lambda ta, names: [0.0]*len(names), raising=True)
    monkeypatch.setattr(runner, "log_unknowns_once", lambda *a, **k: None, raising=True)


# ------------------ Tests ------------------ #

@pytest.mark.django_db
def test_get_ml_weight_fallback_to_default_when_no_db():
    """
    With no MlPreference row, get_ml_weight() must return DEFAULT_ML_WEIGHT.
    """
    # Ensure any existing row is removed
    MlPreference.objects.filter(key="ml_weight").delete()

    w = ml_cfg.get_ml_weight()
    assert pytest.approx(w, rel=1e-9) == ml_cfg.DEFAULT_ML_WEIGHT


@pytest.mark.django_db
def test_get_ml_weight_uses_db_override():
    """
    With MlPreference row present, get_ml_weight() must use DB value.
    """
    MlPreference.objects.update_or_create(key="ml_weight", defaults={"float_value": 0.55})

    w = ml_cfg.get_ml_weight()
    assert pytest.approx(w, rel=1e-9) == 0.55


@pytest.mark.django_db
def test_composite_respects_weight_override_in_runner(monkeypatch):
    """
    End-to-end check: run_ml_on_new_data must use the DB weight,
    affecting the composite score as: (1-w)*rule_conf + w*(max_long_short * 100).
    """
    # Rule confidence and ML prob that make the math obvious:
    rc = 50.0            # rule_confidence (0..100)
    p_long = 0.80        # ML long probability
    # First: default weight (no DB row)
    MlPreference.objects.filter(key="ml_weight").delete()

    _patch_model(monkeypatch, _ModelFixedLongProb(p_long))
    _patch_zero_vectors(monkeypatch)

    ta = _make_ta(rc=rc)
    runner.run_ml_on_new_data(ta.id)
    ta.refresh_from_db()

    w_default = ml_cfg.DEFAULT_ML_WEIGHT
    expected_default = (1.0 - w_default) * rc + w_default * (p_long * 100.0)
    assert pytest.approx(ta.composite_score, rel=1e-6) == expected_default

    # Now: set DB override and re-run on a fresh TA
    MlPreference.objects.update_or_create(key="ml_weight", defaults={"float_value": 0.10})
    ta2 = _make_ta(rc=rc)
    runner.run_ml_on_new_data(ta2.id)
    ta2.refresh_from_db()

    w_override = 0.10
    expected_override = (1.0 - w_override) * rc + w_override * (p_long * 100.0)
    assert pytest.approx(ta2.composite_score, rel=1e-6) == expected_override
