import numpy as np
import pytest
from django.utils import timezone

from backend.models import MarketData, MarketDataFeatures, TradeAnalysis, MlPreference

# Module under test
import celery_tasks.run_ml_on_new_data as runner
from ml_pipeline import ml_model, config as ml_cfg


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


class _ZeroVecBuilder:
    """Monkey builder returning a deterministic zero vector of size n."""
    def __init__(self, n=4):
        self.n = n
    def to_vector_for_ta(self, ta):
        return [0.0] * self.n
    def to_vector_by_feature_names(self, ta, names):
        return [0.0] * len(names)


class _ModelProb:
    def __init__(self, probs, classes=None, n_features=4):
        self._probs = np.array(probs, dtype=float)
        if classes is not None:
            self.classes_ = classes
        self.n_features_in_ = n_features
    def predict_proba(self, X):
        return self._probs.reshape(1, -1)


def _patch_model(monkeypatch, model):
    monkeypatch.setattr(ml_model, "get", lambda: model, raising=True)
    monkeypatch.setattr(ml_model, "get_version", lambda: "v1", raising=True)
    monkeypatch.setattr(ml_model, "get_hash_prefix", lambda: "deadbeef", raising=True)


def _patch_builders(monkeypatch, n=4):
    zb = _ZeroVecBuilder(n)
    monkeypatch.setattr(runner, "to_vector_for_ta", zb.to_vector_for_ta, raising=True)
    monkeypatch.setattr(runner, "to_vector_by_feature_names", zb.to_vector_by_feature_names, raising=True)
    # No feature_names from model
    monkeypatch.setattr(runner, "log_unknowns_once", lambda *a, **k: None, raising=True)


@pytest.mark.django_db
def test_probs_all_zero_composite_equals_rule_when_weight_zero(monkeypatch):
    """Edge: prob=0 for all classes -> composite should equal rule when ml_weight=0."""
    MlPreference.objects.update_or_create(key="ml_weight", defaults={"float_value": 0.0})

    _patch_model(monkeypatch, _ModelProb([0.0, 0.0, 0.0]))
    _patch_builders(monkeypatch, n=4)

    ta = _make_ta(rc=77)
    runner.run_ml_on_new_data(ta.id)
    ta.refresh_from_db()

    assert ta.ml_prob_long == 0.0
    assert ta.ml_prob_short == 0.0
    assert ta.ml_prob_no_trade == 0.0
    assert pytest.approx(ta.composite_score, rel=1e-5) == 77.0  # equals rule_conf when weight=0


@pytest.mark.django_db
def test_prob_full_dominance_long_with_weight_one(monkeypatch):
    """Edge: prob=1.0 dominance for LONG -> ml_confidence 100 and composite==100 when ml_weight=1."""
    MlPreference.objects.update_or_create(key="ml_weight", defaults={"float_value": 1.0})

    _patch_model(monkeypatch, _ModelProb([1.0, 0.0, 0.0]))
    _patch_builders(monkeypatch, n=4)

    ta = _make_ta(rc=60)  # rc >= threshold so ML path runs
    runner.run_ml_on_new_data(ta.id)
    ta.refresh_from_db()

    assert ta.ml_signal == "LONG"
    assert pytest.approx(ta.ml_confidence, rel=1e-6) == 100.0
    # max(long, short)=1.0 => composite 100 when weight=1
    assert pytest.approx(ta.composite_score, rel=1e-6) == 100.0


@pytest.mark.django_db
def test_zero_feature_vector_safe_and_predicts(monkeypatch):
    """Edge: empty/zero feature vectors still produce a valid prediction path."""
    MlPreference.objects.update_or_create(key="ml_weight", defaults={"float_value": 0.3})

    # Binary probs (no classes): trigger two-length heuristic
    _patch_model(monkeypatch, _ModelProb([0.4, 0.6], classes=None, n_features=4))
    _patch_builders(monkeypatch, n=4)

    ta = _make_ta(rc=60)
    runner.run_ml_on_new_data(ta.id)
    ta.refresh_from_db()

    # With [0.4,0.6] heuristic -> short=0.4, long=0.6
    assert pytest.approx(ta.ml_prob_long, rel=1e-6) == 0.6
    assert pytest.approx(ta.ml_prob_short, rel=1e-6) == 0.4
    assert pytest.approx(ta.ml_prob_no_trade, rel=1e-6) == 0.0
    assert ta.ml_signal == "LONG"
    assert 60.0 <= ta.composite_score <= 100.0


@pytest.mark.django_db
def test_rule_primacy_when_weight_zero(monkeypatch):
    """
    Behavioral guarantee: when ml_weight=0, composite must equal rule_confidence
    (covers canonical + legacy alias environments).
    """
    MlPreference.objects.update_or_create(key="ml_weight", defaults={"float_value": 0.0})

    _patch_model(monkeypatch, _ModelProb([0.6, 0.4, 0.0]))
    _patch_builders(monkeypatch, n=4)

    ta = _make_ta(rc=65)  # treat as legacy/canonical source of rule confidence
    runner.run_ml_on_new_data(ta.id)
    ta.refresh_from_db()

    assert pytest.approx(ta.composite_score, rel=1e-6) == 65.0
