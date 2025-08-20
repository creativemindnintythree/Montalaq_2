"""
Agent 011.3 — Explainability Extraction (SHAP + Fallback)

get_top_n_feature_importances(model, n, feature_names=None, X_background=None) → list[dict]
Returns a compact JSON-serializable list like:
    [{"feature": "VWAP distance", "importance": 0.141}, ...]

Rules:
- Try SHAP (if installed & works).
- Else use model.feature_importances_ (tree/boosting models).
- Else use model.coef_ (linear/logistic) and aggregate abs weights.
- If multiclass (2D coef_), reduce by mean(abs(coef), axis=0).
- Sort by absolute importance descending; take top n.
- If feature_names is None, attempt to load ml_pipeline/feature_map.json
  to map index → label; fallback to f"f{i}".
- Clamp n ≥ 1.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional, Sequence

import numpy as np

try:
    import shap  # type: ignore
    _HAS_SHAP = True
except Exception:
    _HAS_SHAP = False

# Default path for labels map
_FEATURE_MAP_PATH = Path(__file__).with_name("feature_map.json")


def _load_feature_labels(m: int) -> List[str]:
    try:
        if _FEATURE_MAP_PATH.exists():
            with open(_FEATURE_MAP_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                max_idx = max(int(k) for k in data.keys())
                labels = [None] * (max_idx + 1)
                for k, v in data.items():
                    idx = int(k)
                    labels[idx] = str(v)
                return [lbl if lbl is not None else f"f{i}" for i, lbl in enumerate(labels)]
            elif isinstance(data, list):
                return [str(x) for x in data]
    except Exception:
        pass
    return [f"f{i}" for i in range(m)]


def _ensure_numpy_1d(a: np.ndarray) -> np.ndarray:
    a = np.asarray(a)
    if a.ndim == 1:
        return a
    if a.ndim == 2:
        return np.mean(np.abs(a), axis=0)
    return a.reshape(-1)


def _get_raw_importances(model, X_background: Optional[np.ndarray] = None) -> Optional[np.ndarray]:
    # 1) SHAP explainability (if available)
    if _HAS_SHAP and X_background is not None:
        try:
            explainer = shap.Explainer(model, X_background)
            shap_values = explainer(X_background[:50])  # sample background subset
            # mean absolute shap values across samples
            arr = np.mean(np.abs(shap_values.values), axis=0)
            return _ensure_numpy_1d(arr)
        except Exception:
            pass

    # 2) Tree/boosted models
    imp = getattr(model, "feature_importances_", None)
    if imp is not None:
        try:
            return _ensure_numpy_1d(np.asarray(imp, dtype=float))
        except Exception:
            pass

    # 3) Linear models
    coef = getattr(model, "coef_", None)
    if coef is not None:
        try:
            return np.abs(_ensure_numpy_1d(np.asarray(coef, dtype=float)))
        except Exception:
            pass

    return None


def get_top_n_feature_importances(
    model,
    n: int,
    feature_names: Optional[Sequence[str]] = None,
    X_background: Optional[np.ndarray] = None,
) -> List[dict]:
    n = max(1, int(n))

    raw = _get_raw_importances(model, X_background)
    if raw is None:
        return []

    m = raw.shape[0]

    if feature_names is not None and len(feature_names) == m:
        labels = [str(x) for x in feature_names]
    else:
        labels = _load_feature_labels(m)
        if len(labels) < m:
            labels = labels + [f"f{i}" for i in range(len(labels), m)]
        elif len(labels) > m:
            labels = labels[:m]

    mags = np.abs(raw)
    order = np.argsort(-mags)

    return [{"feature": labels[idx], "importance": float(mags[idx])} for idx in order[:n]]


if __name__ == "__main__":  # pragma: no cover
    class _Dummy:
        feature_importances_ = np.array([0.2, 0.1, 0.5, 0.2])

    demo = _Dummy()
    print(get_top_n_feature_importances(demo, 3))
