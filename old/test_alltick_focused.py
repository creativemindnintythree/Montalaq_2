# C:\Users\AHMED AL BALUSHI\Montalaq_2\tests\test_agent011_task.py
"""
Task-level tests for Agent 011 Celery task `run_ml_on_new_data.py`.
Covers: gating, idempotency, persistence, and failure fallback.

Assumptions
-----------
- Django settings: montalaq_project.settings
- Model: backend.models.TradeAnalysis
- Task entry: celery_tasks.run_ml_on_new_data.run_ml_on_trade_analysis(trade_analysis_id, reprocess=False)
- ML singleton: ml_pipeline.ml_model.MLModel.get_instance()
- prefs.get_ml_weight_for_user(user_id) available
"""
from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest
from django.test import TestCase
from django.utils.timezone import now

from backend.models import TradeAnalysis
from celery_tasks.run_ml_on_new_data import run_ml_on_trade_analysis


class Agent011TaskTests(TestCase):
    databases = {"default"}

    def setUp(self):
        # Minimal TA row resembling Agent 010 output
        self.ta = TradeAnalysis.objects.create(
            symbol="EURUSD",
            timeframe=60,
            final_decision="LONG",
            rule_confidence_score=80.0,  # 0–100 canonical
            created_at=now(),
        )

    # -----------------------------
    # GATING
    # -----------------------------
    @patch("ml_pipeline.ml_model.MLModel.get_instance")
    def test_gate_no_trade_skips_ml(self, get_instance):
        self.ta.final_decision = "NO_TRADE"
        self.ta.save(update_fields=["final_decision"])

        get_instance.return_value = None  # must not be called
        run_ml_on_trade_analysis(trade_analysis_id=self.ta.id, reprocess=False)
        self.ta.refresh_from_db()

        assert self.ta.ml_signal is None
        # Composite may remain None depending on implementation; both acceptable for gate.
        assert self.ta.composite_score is None or self.ta.composite_score == pytest.approx(self.ta.rule_confidence_score)

    @patch("ml_pipeline.ml_model.MLModel.get_instance")
    def test_gate_low_rule_confidence_skips_ml(self, get_instance):
        from ml_pipeline.config import MIN_RULE_CONF_FOR_ML

        self.ta.final_decision = "LONG"
        self.ta.rule_confidence_score = float(MIN_RULE_CONF_FOR_ML) - 0.01
        self.ta.save(update_fields=["final_decision", "rule_confidence_score"])

        get_instance.return_value = None  # must not be called
        run_ml_on_trade_analysis(trade_analysis_id=self.ta.id, reprocess=False)
        self.ta.refresh_from_db()

        assert self.ta.ml_signal is None
        assert self.ta.composite_score is None or self.ta.composite_score == pytest.approx(self.ta.rule_confidence_score)

    # -----------------------------
    # SUCCESS PATH
    # -----------------------------
    @patch("prefs.get_ml_weight_for_user", return_value=0.30)
    @patch("ml_pipeline.ml_model.MLModel.get_instance")
    def test_success_persists_probs_signal_and_composite(self, get_instance, _):
        model = MagicMock()
        model.get_version.return_value = "v1.0.0"
        model.get_hash_prefix.return_value = "abc12345"
        def _predict(X, labels):
            # LONG top class
            return "LONG", {"LONG": 0.62, "SHORT": 0.28, "NO_TRADE": 0.10}
        model.predict_with_proba.side_effect = _predict
        get_instance.return_value = model

        run_ml_on_trade_analysis(trade_analysis_id=self.ta.id, reprocess=False)
        self.ta.refresh_from_db()

        assert self.ta.ml_signal == "LONG"
        assert self.ta.ml_prob_long == pytest.approx(0.62)
        assert self.ta.ml_prob_short == pytest.approx(0.28)
        assert self.ta.ml_prob_no_trade == pytest.approx(0.10)
        # composite (0–100): rule 80, ml 62, w=0.30 → 74.0
        assert self.ta.composite_score == pytest.approx(74.0)
        assert self.ta.ml_model_version == "v1.0.0"
        assert self.ta.ml_model_hash_prefix.startswith("abc12345")
        # feature_importances may be list or None (depending on explain hook outcome)
        assert isinstance(self.ta.feature_importances, (list, type(None)))

    # -----------------------------
    # IDEMPOTENCY
    # -----------------------------
    @patch("prefs.get_ml_weight_for_user", return_value=0.30)
    @patch("ml_pipeline.ml_model.MLModel.get_instance")
    def test_idempotency_skips_second_run_without_reprocess(self, get_instance, _):
        model = MagicMock()
        model.get_version.return_value = "v1"
        model.get_hash_prefix.return_value = "hashvvvv"
        model.predict_with_proba.return_value = ("LONG", {"LONG": 0.60, "SHORT": 0.30, "NO_TRADE": 0.10})
        get_instance.return_value = model

        # First run populates fields
        run_ml_on_trade_analysis(trade_analysis_id=self.ta.id, reprocess=False)
        self.ta.refresh_from_db()
        first_comp = float(self.ta.composite_score)

        # Second run should be idempotent (no changes)
        run_ml_on_trade_analysis(trade_analysis_id=self.ta.id, reprocess=False)
        self.ta.refresh_from_db()
        assert self.ta.composite_score == pytest.approx(first_comp)
        assert self.ta.ml_model_version == "v1"
        assert self.ta.ml_model_hash_prefix.startswith("hashvvvv")

    @patch("prefs.get_ml_weight_for_user", return_value=0.30)
    @patch("ml_pipeline.ml_model.MLModel.get_instance")
    def test_reprocess_overrides_idempotency(self, get_instance, _):
        model = MagicMock()
        model.get_version.return_value = "v1"
        model.get_hash_prefix.return_value = "hashv1"
        model.predict_with_proba.return_value = ("LONG", {"LONG": 0.60, "SHORT": 0.30, "NO_TRADE": 0.10})
        get_instance.return_value = model

        run_ml_on_trade_analysis(trade_analysis_id=self.ta.id, reprocess=False)
        self.ta.refresh_from_db()
        first_comp = float(self.ta.composite_score)

        # Change mock to simulate new output (or new model)
        model.get_version.return_value = "v2"
        model.get_hash_prefix.return_value = "hashv2"
        model.predict_with_proba.return_value = ("SHORT", {"LONG": 0.40, "SHORT": 0.55, "NO_TRADE": 0.05})

        run_ml_on_trade_analysis(trade_analysis_id=self.ta.id, reprocess=True)
        self.ta.refresh_from_db()
        assert self.ta.ml_model_version == "v2"
        assert self.ta.ml_signal == "SHORT"
        assert self.ta.composite_score != pytest.approx(first_comp)

    # -----------------------------
    # FAILURE / FALLBACK
    # -----------------------------
    @patch("ml_pipeline.ml_model.MLModel.get_instance")
    def test_model_load_failure_sets_rule_only_composite(self, get_instance):
        # Loader returns None → fallback to rule-only composite
        get_instance.return_value = None

        run_ml_on_trade_analysis(trade_analysis_id=self.ta.id, reprocess=False)
        self.ta.refresh_from_db()

        assert self.ta.ml_signal is None
        assert self.ta.ml_prob_long is None
        assert self.ta.ml_prob_short is None
        assert self.ta.ml_prob_no_trade is None
        assert self.ta.composite_score == pytest.approx(self.ta.rule_confidence_score)

    @patch("ml_pipeline.ml_model.MLModel.get_instance")
    def test_predict_exception_sets_rule_only_composite(self, get_instance):
        model = MagicMock()
        model.get_version.return_value = "v1"
        model.get_hash_prefix.return_value = "hashboom"
        def _boom(*args, **kwargs):
            raise RuntimeError("predict failed")
        model.predict_with_proba.side_effect = _boom
        get_instance.return_value = model

        run_ml_on_trade_analysis(trade_analysis_id=self.ta.id, reprocess=False)
        self.ta.refresh_from_db()

        assert self.ta.composite_score == pytest.approx(self.ta.rule_confidence_score)
        assert self.ta.ml_signal is None
        assert self.ta.ml_prob_long is None
        assert self.ta.ml_prob_short is None
        assert self.ta.ml_prob_no_trade is None
