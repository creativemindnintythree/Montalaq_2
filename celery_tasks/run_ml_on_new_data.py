from typing import List, Optional
from django.db import transaction
from backend.models import TradeAnalysis
from ml_pipeline import config as ml_cfg
from ml_pipeline import ml_model
from ml_pipeline import explain  # NEW: explainability hooks

# Vector builders
from ml_pipeline.feature_builder import (
    to_vector_for_ta,
    to_vector_by_feature_names,
    log_unknowns_once,
)

try:
    from lightgbm.basic import LightGBMError  # type: ignore
except Exception:
    class LightGBMError(Exception):
        pass


def _compute_composite(rule_conf: float, ml_prob: float, weight: float) -> float:
    """Blend rule confidence (0..100) with ML prob (0..1) into 0..100."""
    comp = (1.0 - weight) * rule_conf + weight * (ml_prob * 100.0)
    return max(0.0, min(100.0, comp))


def _expected_num_features(model) -> Optional[int]:
    """Infer the model's expected feature count (works for sklearn wrappers and raw LightGBM Booster)."""
    n = getattr(model, "n_features_in_", None)
    if isinstance(n, int) and n > 0:
        return n
    booster = getattr(model, "booster_", None)
    if booster is not None and hasattr(booster, "num_feature"):
        try:
            return int(booster.num_feature())
        except Exception:
            pass
    if hasattr(model, "num_feature"):
        try:
            return int(model.num_feature())
        except Exception:
            pass
    return None


def _persist_rule_only(ta: TradeAnalysis, rc: float) -> None:
    with transaction.atomic():
        ta.composite_score = rc
        ta.ml_signal = None
        ta.ml_confidence = None
        ta.ml_prob_long = None
        ta.ml_prob_short = None
        ta.ml_prob_no_trade = None
        ta.ml_model_version = ml_model.get_version()
        ta.ml_model_hash_prefix = ml_model.get_hash_prefix()
        ta.top_features = None  # clear explainability if no ML run
        ta.save(update_fields=[
            "composite_score",
            "ml_signal", "ml_confidence",
            "ml_prob_long", "ml_prob_short", "ml_prob_no_trade",
            "ml_model_version", "ml_model_hash_prefix",
            "top_features",
        ])


def run_ml_on_new_data(trade_analysis_id: int) -> None:
    ta = TradeAnalysis.objects.select_for_update().get(id=trade_analysis_id)

    # Canonical rules confidence (Agent 010)
    rc = float(getattr(ta, "rule_confidence", None) or getattr(ta, "rule_confidence_score", 0.0) or 0.0)

    # GATE: only run ML if rules say it's a potential trade and confidence is sufficient
    if ta.final_decision == ml_cfg.SIGNAL_NO_TRADE or rc < ml_cfg.MIN_RULE_CONF_FOR_ML:
        _persist_rule_only(ta, rc)
        return

    model = ml_model.get()
    if model is None:
        _persist_rule_only(ta, rc)
        return

    # Discover the model's feature names if possible
    feature_names = None
    booster = getattr(model, "booster_", None)
    if booster is not None and hasattr(booster, "feature_name"):
        try:
            feature_names = list(booster.feature_name())
        except Exception:
            feature_names = None
    elif hasattr(model, "feature_name"):
        try:
            feature_names = list(model.feature_name())
        except Exception:
            feature_names = None

    # Log unknowns once so we can extend MODEL_TO_DB_NAME_MAP as needed
    log_unknowns_once(feature_names, getattr(ta, "market_data_feature", None))

    # Build feature vector (prefer model-declared names)
    if feature_names:
        vec = to_vector_by_feature_names(ta, feature_names)
    else:
        vec = to_vector_for_ta(ta)
    X = [vec]  # 2D for sklearn-like APIs

    # Pre-check feature count and gracefully fallback on mismatch
    expected = _expected_num_features(model)
    if isinstance(expected, int) and expected != len(vec):
        _persist_rule_only(ta, rc)
        return

    # Predict probabilities or scores
    try:
        if hasattr(model, "predict_proba"):
            raw = model.predict_proba(X)
            probs = list(raw[0]) if hasattr(raw, "__getitem__") else [float(raw)]
            labels = list(getattr(model, "classes_", []))
        else:
            raw = model.predict(X)
            score = float(raw[0]) if hasattr(raw, "__getitem__") else float(raw)
            probs = [score]
            labels = []
    except (LightGBMError, Exception):
        _persist_rule_only(ta, rc)
        return

    # ---- Normalize classes -> canonical {LONG, SHORT, NO_TRADE} ----
    def _canon_label(lbl):
        s = str(lbl).strip().lower()
        if any(k in s for k in ["long", "buy", "bull", "up", "+1", "1", "pos"]):
            return "LONG"
        if any(k in s for k in ["short", "sell", "bear", "down", "-1", "neg"]):
            return "SHORT"
        if any(k in s for k in ["no", "none", "hold", "flat", "0", "neutral"]):
            return "NO_TRADE"
        return None

    p_long = p_short = p_none = 0.0

    if labels and len(labels) == len(probs):
        for lbl, pr in zip(labels, probs):
            canon = _canon_label(lbl)
            if canon == "LONG":
                p_long = float(pr)
            elif canon == "SHORT":
                p_short = float(pr)
            elif canon == "NO_TRADE":
                p_none = float(pr)

    if (p_long, p_short, p_none) == (0.0, 0.0, 0.0):
        if len(probs) == 3:
            p_long, p_short, p_none = float(probs[0]), float(probs[1]), float(probs[2])
        elif len(probs) == 2:
            p_short, p_long = float(probs[0]), float(probs[1])
            p_none = 0.0
        elif len(probs) == 1:
            p_long = float(probs[0])
            p_short = 1.0 - p_long
            p_none = 0.0

    p_long = max(0.0, min(1.0, p_long))
    p_short = max(0.0, min(1.0, p_short))
    p_none = max(0.0, min(1.0, p_none))

    if p_long >= max(p_short, p_none):
        best_signal, ml_prob = "LONG", p_long
    elif p_short >= max(p_long, p_none):
        best_signal, ml_prob = "SHORT", p_short
    else:
        best_signal, ml_prob = "NO_TRADE", 0.0

    ml_conf_pct = ml_prob * 100.0

    weight = getattr(ml_cfg, "DEFAULT_ML_WEIGHT", 0.30)
    composite = _compute_composite(rc, float(max(p_long, p_short)), float(weight))

    # ---- Explainability hook ----
    try:
        top_feats = explain.get_top_n_feature_importances(
            model,
            n=getattr(ml_cfg, "TOP_N_FEATURES", 5),
            feature_names=feature_names,
            X_background=np.array(X) if "np" in globals() else None,
        )
    except Exception:
        top_feats = []

    with transaction.atomic():
        ta.ml_signal = best_signal
        ta.ml_confidence = ml_conf_pct
        ta.ml_prob_long = p_long
        ta.ml_prob_short = p_short
        ta.ml_prob_no_trade = p_none
        ta.ml_model_version = ml_model.get_version()
        ta.ml_model_hash_prefix = ml_model.get_hash_prefix()
        ta.composite_score = composite
        ta.top_features = top_feats or None
        ta.save(update_fields=[
            "ml_signal", "ml_confidence", "ml_prob_long", "ml_prob_short", "ml_prob_no_trade",
            "ml_model_version", "ml_model_hash_prefix", "composite_score", "top_features",
        ])

    print(f"[ML-Runner] TA={ta.id} rc={rc:.2f} ml={ml_conf_pct:.2f}% comp={composite:.2f}")
