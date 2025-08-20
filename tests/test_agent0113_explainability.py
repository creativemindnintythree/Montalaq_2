import numpy as np
import pytest
from django.utils import timezone

from backend.models import MarketData, MarketDataFeatures, TradeAnalysis, MlPreference

# Module under test
import celery_tasks.run_ml_on_new_data as runner
from ml_pipeline import ml_model, config as ml_cfg, explain


@pytest.mark.django_db
def _make_ta(symbol="EURUSD", rc=70, decision=None):
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


class _ZeroVecBuilder:
    def __init__(self, n=4):
        self.n = n
    def to_vector_for_ta(self, ta):
        return [0.0] * self.n
    def to_vector_by_feature_names(self, ta, names):
        return [0.0] * len(names)


def _patch_builders(monkeypatch, n=4):
    zb = _ZeroVecBuilder(n)
    monkeypatch.setattr(runner, "to_vector_for_ta", zb.to_vector_for_ta, raising=True)
    monkeypatch.setattr(runner, "to_vector_by_feature_names", zb.to_vector_by_feature_names, raising=True)
    monkeypatch.setattr(runner, "log_unknowns_once", lambda *a, **k: None, raising=True)


class _ModelWithProba:
    def __init__(self, probs, n_features=4):
        self._probs = np.array(probs, dtype=float)
        self.n_features_in_ = n_features
    def predict_proba(self, X):
        return self._probs.reshape(1, -1)


class _ModelWithFI(_ModelWithProba):
    def __init__(self, probs, fi, n_features=4):
        super().__init__(probs, n_features=n_features)
        self.feature_importances_ = np.array(fi, dtype=float)


def _patch_model(monkeypatch, model):
    monkeypatch.setattr(ml_model, "get", lambda: model, raising=True)
    monkeypatch.setattr(ml_model, "get_version", lambda: "v1", raising=True)
    monkeypatch.setattr(ml_model, "get_hash_prefix", lambda: "beefcafe", raising=True)


@pytest.mark.django_db
def test_top_features_saved_when_shap_available(monkeypatch):
    """Mock SHAP path by monkeypatching explain.get_top_n_feature_importances."""
    MlPreference.objects.update_or_create(key="ml_weight", defaults={"float_value": 0.3})

    # Deterministic explainability output (pretend SHAP)
    expected = [
        {"feature": "rsi_14", "importance": 0.42},
        {"feature": "ema_20", "importance": 0.33},
    ]
    monkeypatch.setattr(explain, "get_top_n_feature_importances", lambda *a, **k: expected, raising=True)

    # Model returns strong LONG so we also exercise save path
    _patch_model(monkeypatch, _ModelWithProba([0.9, 0.1, 0.0]))
    _patch_builders(monkeypatch, n=4)

    ta = _make_ta(rc=70)
    runner.run_ml_on_new_data(ta.id)
    ta.refresh_from_db()

    assert isinstance(ta.top_features, list) and len(ta.top_features) == 2
    assert ta.top_features[0]["feature"] == "rsi_14"
    assert pytest.approx(ta.top_features[0]["importance"], rel=1e-6) == 0.42


@pytest.mark.django_db
def test_top_features_saved_via_feature_importances_fallback(monkeypatch):
    """Force fallback (no SHAP) and ensure feature_importances_ are used to persist top_features."""
    MlPreference.objects.update_or_create(key="ml_weight", defaults={"float_value": 0.3})

    # Ensure fallback path is used inside explain
    monkeypatch.setattr(explain, "_HAS_SHAP", False, raising=True)

    # Model with feature_importances_
    fi = [0.1, 0.5, 0.3, 0.1]
    model = _ModelWithFI([0.7, 0.3, 0.0], fi, n_features=4)
    _patch_model(monkeypatch, model)
    _patch_builders(monkeypatch, n=4)

    ta = _make_ta(rc=70)
    runner.run_ml_on_new_data(ta.id)
    ta.refresh_from_db()

    assert isinstance(ta.top_features, list) and len(ta.top_features) > 0
    # Highest FI should be first
    assert pytest.approx(ta.top_features[0]["importance"], rel=1e-6) == max(fi)
