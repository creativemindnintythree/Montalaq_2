# tests/test_agent011_task.py
# Task-level tests for Agent 011 without touching the real DB or model files.

import types
import sys
import pytest
import importlib

# ------------------------------
# Fakes and helpers
# ------------------------------
class SaveSpy:
    def __init__(self, obj):
        self.obj = obj
        self.calls = 0
    def __call__(self, *args, **kwargs):
        self.calls += 1

class FakeTA:
    def __init__(
        self,
        id=1,
        final_decision="LONG",
        rule_confidence_score=80.0,
        composite_score=None,
        ml_signal=None,
        ml_prob_long=None,
        ml_prob_short=None,
        ml_prob_no_trade=None,
        ml_model_version=None,
        ml_model_hash_prefix=None,
        feature_importances=None,
    ):
        self.id = id
        self.final_decision = final_decision
        self.rule_confidence_score = rule_confidence_score
        self.composite_score = composite_score
        self.ml_signal = ml_signal
        self.ml_prob_long = ml_prob_long
        self.ml_prob_short = ml_prob_short
        self.ml_prob_no_trade = ml_prob_no_trade
        self.ml_model_version = ml_model_version
        self.ml_model_hash_prefix = ml_model_hash_prefix
        self.feature_importances = feature_importances
        self.provider_used = None
        self._save_spy = SaveSpy(self)
    def save(self):
        return self._save_spy()

class _Objects:
    def __init__(self):
        self._row = None
    def get(self, id):
        if self._row is None:
            self._row = FakeTA(id=id)
        return self._row
    def set_row(self, row):
        self._row = row

@pytest.fixture
def fake_backend_tradeanalysis(monkeypatch):
    """Install a fake backend.models.TradeAnalysis into sys.modules BEFORE importing the task."""
    fake_models = types.SimpleNamespace()
    objs = _Objects()
    class TradeAnalysis:
        objects = objs
    fake_models.TradeAnalysis = TradeAnalysis
    sys.modules["backend.models"] = fake_models
    return objs

@pytest.fixture
def fake_config():
    cfg = types.SimpleNamespace(
        DEFAULT_ML_WEIGHT=0.30,
        MIN_RULE_CONF_FOR_ML=40.0,
        TOP_N_FEATURES=5,
        LABEL_LONG="LONG",
        LABEL_SHORT="SHORT",
        LABEL_NO_TRADE="NO_TRADE",
    )
    sys.modules["ml_pipeline.config"] = cfg
    return cfg

@pytest.fixture
def fake_composite(fake_config):
    def compute_composite(rule_score_pct, ml_prob_pct, ml_weight):
        r = max(0.0, min(100.0, float(rule_score_pct or 0.0)))
        m = max(0.0, min(100.0, float(ml_prob_pct or 0.0)))
        w = max(0.0, min(1.0, float(ml_weight if ml_weight is not None else fake_config.DEFAULT_ML_WEIGHT)))
        return (r * (1 - w)) + (m * w)
    sys.modules["ml_pipeline.composite"] = types.SimpleNamespace(compute_composite=compute_composite)

@pytest.fixture
def fake_prefs():
    def get_ml_weight_for_user(user_id=None):
        return None  # forces fallback to DEFAULT_ML_WEIGHT
    sys.modules["prefs"] = types.SimpleNamespace(get_ml_weight_for_user=get_ml_weight_for_user)

@pytest.fixture
def fake_mlmodel(fake_config):
    class _FakeModel:
        def __init__(self, v="vtest", h="abc12345"):
            self._v = v; self._h = h
        def get_version(self): return self._v
        def get_hash_prefix(self): return self._h
        def predict(self, X):
            return {
                "label": fake_config.LABEL_LONG,
                "probs": {"LONG": 0.62, "SHORT": 0.30, "NO_TRADE": 0.08},
                "top_features": [
                    {"feature": "atr_14", "importance": 0.41},
                    {"feature": "ema_8_vs_20", "importance": 0.22},
                ],
            }
    singleton = {"m": _FakeModel()}
    def get_model():
        return singleton["m"]
    sys.modules["ml_pipeline.ml_model"] = types.SimpleNamespace(get_model=get_model)
    return singleton  # so tests can swap version/hash if needed

@pytest.fixture
def task_module(fake_backend_tradeanalysis, fake_config, fake_composite, fake_prefs, fake_mlmodel):
    """
    Import the real celery_tasks.run_ml_on_new_data AFTER fakes are in place
    so its 'from backend.models import TradeAnalysis' etc. resolve to our fakes.
    """
    modname = "celery_tasks.run_ml_on_new_data"
    if modname in sys.modules:
        del sys.modules[modname]
    mod = importlib.import_module(modname)
    return mod

# ------------------------------
# Tests
# ------------------------------
def test_gate_on_no_trade(task_module, fake_backend_tradeanalysis, fake_config):
    row = FakeTA(id=101, final_decision=fake_config.LABEL_NO_TRADE, rule_confidence_score=85.0)
    fake_backend_tradeanalysis.set_row(row)

    task_module.run_ml_on_new_data(trade_analysis_id=101, reprocess=False, user_id=1)

    assert row.ml_signal is None
    assert row.ml_prob_long is None
    assert row.ml_prob_short is None
    assert row.ml_prob_no_trade is None
    # Gate path typically skips composite; both None or rule-only are acceptable depending on implementation
    assert row.composite_score is None or row.composite_score == row.rule_confidence_score
    assert row._save_spy.calls == 0

def test_idempotency_same_version_skips(task_module, fake_backend_tradeanalysis):
    row = FakeTA(
        id=202,
        final_decision="LONG",
        rule_confidence_score=80.0,
        ml_signal="LONG",
        ml_prob_long=0.60,
        ml_prob_short=0.30,
        ml_prob_no_trade=0.10,
        composite_score=74.0,
        ml_model_version="vtest",
        ml_model_hash_prefix="abc12345",
    )
    fake_backend_tradeanalysis.set_row(row)

    task_module.run_ml_on_new_data(trade_analysis_id=202, reprocess=False, user_id=1)

    assert row._save_spy.calls == 0
    assert row.composite_score == 74.0
    assert row.ml_signal == "LONG"

def test_normal_persistence(task_module, fake_backend_tradeanalysis):
    row = FakeTA(id=303, final_decision="LONG", rule_confidence_score=80.0)
    fake_backend_tradeanalysis.set_row(row)

    task_module.run_ml_on_new_data(trade_analysis_id=303, reprocess=False, user_id=42)

    assert row._save_spy.calls >= 1
    assert row.ml_signal == "LONG"
    assert row.ml_prob_long == pytest.approx(0.62)
    assert row.ml_prob_short == pytest.approx(0.30)
    assert row.ml_prob_no_trade == pytest.approx(0.08)
    # composite 0–100, ml prob ×100 then blend with default 0.30 weight -> 80*0.7 + 62*0.3 = 56 + 18.6 = 74.6
    assert row.composite_score == pytest.approx(74.6)
    assert row.ml_model_version == "vtest"
    assert row.ml_model_hash_prefix == "abc12345"
    assert isinstance(row.feature_importances, (list, type(None))) or row.feature_importances is None
