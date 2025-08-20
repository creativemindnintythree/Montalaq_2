import logging
import numpy as np
import pytest
from django.utils import timezone

from backend.models import MarketData, MarketDataFeatures, TradeAnalysis, MlPreference
from backend.tasks_ml_batch import batch_run_recent
import celery_tasks.run_ml_on_new_data as runner
from ml_pipeline import ml_model, config as ml_cfg


# ---------- Helpers to create valid rows ----------

@pytest.mark.django_db
def _make_ta(rc=60, final_decision=ml_cfg.SIGNAL_LONG, minutes_ago=1):
    ts = timezone.now() - timezone.timedelta(minutes=minutes_ago)
    md = MarketData.objects.create(
        timestamp=ts,
        symbol="EURUSD",
        open=1.0, high=1.0, low=1.0, close=1.0, volume=1.0, provider="test",
    )
    mdf = MarketDataFeatures.objects.create(market_data=md)
    ta = TradeAnalysis.objects.create(
        market_data_feature=mdf,
        timestamp=ts,
        rule_confidence=rc,
        final_decision=final_decision,
    )
    return ta


# ---------- Test doubles for model & vector builders ----------

class _ModelProba:
    """Minimal model returning fixed 3-class probabilities."""
    def __init__(self, probs, n_features=4):
        self._probs = np.array(probs, dtype=float)
        self.n_features_in_ = n_features
    def predict_proba(self, X):
        return self._probs.reshape(1, -1)


def _patch_model(monkeypatch, model):
    monkeypatch.setattr(ml_model, "get", lambda: model, raising=True)
    monkeypatch.setattr(ml_model, "get_version", lambda: "v1", raising=True)
    monkeypatch.setattr(ml_model, "get_hash_prefix", lambda: "deadbeef", raising=True)


def _patch_zero_vec_builders(monkeypatch, n=4):
    # Force the runner's vector builders to return deterministic zero vectors
    monkeypatch.setattr(runner, "to_vector_for_ta", lambda ta: [0.0] * n, raising=True)
    monkeypatch.setattr(runner, "to_vector_by_feature_names",
                        lambda ta, names: [0.0] * len(names), raising=True)
    monkeypatch.setattr(runner, "log_unknowns_once", lambda *a, **k: None, raising=True)


# ------------------ Tests ------------------ #

@pytest.mark.django_db
def test_no_trades_recent(capsys):
    """Batch runner should log a warning but not crash when no trades exist."""
    processed = batch_run_recent(limit=3, minutes=15)
    assert processed == 0
    # Our logger writes to stderr (own handler, propagate=False), so use capsys
    err = capsys.readouterr().err.lower()
    assert "no trades found" in err


@pytest.mark.django_db
def test_missing_features_safe(monkeypatch):
    """
    Even with all-zero vectors (simulate missing/degenerate features),
    batch should still process without crashing.
    """
    # Prepare one eligible TA in window
    _make_ta(rc=60, final_decision=ml_cfg.SIGNAL_LONG, minutes_ago=1)

    # Patch model + builders for a stable run (60% LONG, 40% SHORT)
    _patch_model(monkeypatch, _ModelProba([0.6, 0.4, 0.0]))
    _patch_zero_vec_builders(monkeypatch)

    processed = batch_run_recent(limit=5, minutes=15)
    assert processed == 1  # exactly the single eligible TA


@pytest.mark.django_db
def test_top_features_persisted_via_batch(monkeypatch):
    """
    Ensure explainability writes to TradeAnalysis.top_features via batch runner.
    """
    # One eligible TA
    ta = _make_ta(rc=70, final_decision=ml_cfg.SIGNAL_LONG, minutes_ago=1)

    # Patch model to have feature_importances_ so explain fallback works
    class _ModelWithFI(_ModelProba):
        def __init__(self, probs, fi, n_features=4):
            super().__init__(probs, n_features=n_features)
            self.feature_importances_ = np.array(fi, dtype=float)

    model = _ModelWithFI([0.9, 0.1, 0.0], fi=[0.1, 0.5, 0.3, 0.1], n_features=4)
    _patch_model(monkeypatch, model)
    _patch_zero_vec_builders(monkeypatch)

    processed = batch_run_recent(limit=5, minutes=15)
    assert processed == 1

    ta.refresh_from_db()
    assert isinstance(ta.top_features, list) and len(ta.top_features) >= 1


@pytest.mark.django_db
def test_weight_default_used_when_no_db_entry():
    MlPreference.objects.filter(key="ml_weight").delete()
    w = ml_cfg.get_ml_weight()
    assert isinstance(w, float)
    # After clamping, default is guaranteed within [0,1]
    assert 0.0 <= w <= 1.0
    assert w == ml_cfg.DEFAULT_ML_WEIGHT


@pytest.mark.django_db
def test_weight_runtime_override_reflected():
    MlPreference.objects.update_or_create(key="ml_weight", defaults={"float_value": 0.33})
    w = ml_cfg.get_ml_weight()
    assert pytest.approx(w, rel=1e-9) == 0.33


@pytest.mark.django_db
def test_weight_invalid_values_are_clamped():
    # Above 1 -> clamp to 1.0
    MlPreference.objects.update_or_create(key="ml_weight", defaults={"float_value": 5.0})
    assert ml_cfg.get_ml_weight() == 1.0

    # Below 0 -> clamp to 0.0
    MlPreference.objects.update_or_create(key="ml_weight", defaults={"float_value": -0.5})
    assert ml_cfg.get_ml_weight() == 0.0
