# ml_pipeline/feature_builder.py — Agent 011.2 Step 10
# Goal: build vectors that exactly match the model's training feature order (23 features)
# - Keep to_vector_for_ta() for fallback
# - Add to_vector_by_feature_names() aligned to model feature names
# - Zero-fill missing values so inference never crashes

from typing import List, Dict
from backend.models import TradeAnalysis, MarketDataFeatures

# -----------------------------------------------------------------------------
# Fallback list (minimal set we had live).
# -----------------------------------------------------------------------------
FEATURE_ORDER: List[str] = [
    "atr_14",
    "ema_8",
    "ema_20",
    "ema_50",
    "rsi_14",
    "bb_bandwidth",
]


def to_vector_for_ta(ta: TradeAnalysis) -> List[float]:
    mdf = getattr(ta, "market_data_feature", None)
    if isinstance(mdf, MarketDataFeatures):
        return [float(getattr(mdf, name, 0.0) or 0.0) for name in FEATURE_ORDER]
    return [0.0 for _ in FEATURE_ORDER]


# -----------------------------------------------------------------------------
# Step 10: Full feature alignment (23 features)
# -----------------------------------------------------------------------------
MODEL_TO_DB_NAME_MAP: Dict[str, str] = {
    # Technical indicators (from MarketDataFeatures)
    "atr_14": "atr_14",
    "ema_8": "ema_8",
    "ema_20": "ema_20",
    "ema_50": "ema_50",
    "rsi_14": "rsi_14",
    "bb_bandwidth": "bb_bandwidth",
    "vwap": "vwap",
    "vwap_dist": "vwap_dist",
    "volume_zscore": "volume_zscore",
    "range_atr_ratio": "range_atr_ratio",
    "stoch_k": "stoch_k",
    "stoch_d": "stoch_d",
    "macd": "macd",
    "macd_signal": "macd_signal",
    "adx": "adx",
    "cci": "cci",
    "obv": "obv",
    "willr": "willr",

    # Raw OHLCV (from MarketData via md. prefix)
    "open": "md.open",
    "high": "md.high",
    "low": "md.low",
    "close": "md.close",
    "volume": "md.volume",
}


def _get_mdf_for_ta(ta: TradeAnalysis) -> MarketDataFeatures | None:
    mdf = getattr(ta, "market_data_feature", None)
    return mdf if isinstance(mdf, MarketDataFeatures) else None


def _normalize_name(name: str) -> str:
    return name.replace("-", "_").replace(".", "_").strip().lower()


def to_vector_by_feature_names(ta: TradeAnalysis, model_feature_names: List[str]) -> List[float]:
    mdf = _get_mdf_for_ta(ta)
    if mdf is None:
        return [0.0 for _ in model_feature_names]

    md = getattr(mdf, "market_data", None)

    def _resolve_value(db_name: str) -> float:
        try:
            if db_name.startswith("md."):
                if md is None:
                    return 0.0
                attr = db_name.split(".", 1)[1]
                val = getattr(md, attr, 0.0)
                return float(val) if val is not None else 0.0
            val = getattr(mdf, db_name, 0.0)
            return float(val) if val is not None else 0.0
        except Exception:
            return 0.0

    out: List[float] = []
    for fname in model_feature_names:
        db_name = MODEL_TO_DB_NAME_MAP.get(fname)
        if db_name is None:
            key = _normalize_name(fname)
            db_name = MODEL_TO_DB_NAME_MAP.get(key, key)
        out.append(_resolve_value(db_name))
    return out


# --- one-time logging of unknown feature names ---
import sys
_UNKNOWN_LOGGED = False

def log_unknowns_once(model_feature_names, mdf_obj) -> None:
    global _UNKNOWN_LOGGED
    if _UNKNOWN_LOGGED or not model_feature_names:
        return
    known = set(MODEL_TO_DB_NAME_MAP.keys()) | {k.lower() for k in MODEL_TO_DB_NAME_MAP.keys()}
    unknown = []
    for fname in model_feature_names:
        key = _normalize_name(fname)
        if key not in known and key not in MODEL_TO_DB_NAME_MAP and not hasattr(mdf_obj, key):
            unknown.append(fname)
    if unknown:
        print(f"[Agent011.2] Unknown model feature names (map these in MODEL_TO_DB_NAME_MAP): {unknown}", file=sys.stderr)
        sys.stderr.flush()
    _UNKNOWN_LOGGED = True
