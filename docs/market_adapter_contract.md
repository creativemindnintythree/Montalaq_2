# Market Adapter Contract

**Agent 010 – Rule-Based Analysis Engine**

*Last updated: 13-Aug-2025*

This document defines the exact structure and data types required for the `market` dictionary that is passed from Agents 012 (Data Ingestion) / 013 (Pipeline Orchestration) to Agent 010’s rule evaluation functions.

All fields are **snake_case**.

---

## 1. OHLCV Core Data

| Key       | Type  | Example                                                               | Required | Description                              |
| --------- | ----- | --------------------------------------------------------------------- | -------- | ---------------------------------------- |
| `open`    | float | 1.1045                                                                | ✅        | Current candle open price                |
| `high`    | float | 1.1062                                                                | ✅        | Current candle high price                |
| `low`     | float | 1.1030                                                                | ✅        | Current candle low price                 |
| `close`   | float | 1.1050                                                                | ✅        | Current candle close price               |
| `volume`  | float | 120345.0                                                              | ✅        | Raw volume for the candle                |
| `candles` | list  | `[{"open":1.1035, "high":1.1060, "low":1.1025, "close":1.1050}, ...]` | ✅        | List of most recent candles (min last 3) |

---

## 2. Price/Volume Context Features (Stage 1.1)

| Key          | Type  | Example            | Required | Description                   |
| ------------ | ----- | ------------------ | -------- | ----------------------------- |
| `volume_z`   | float | 1.35               | ✅        | Z-score of volume vs lookback |
| `atr`        | float | 0.0012             | ✅        | Average True Range            |
| `key_levels` | list  | `[1.1000, 1.1050]` | ✅        | Support/resistance levels     |
| `last_pdh`   | float | 1.1068             | ✅        | Prior Day High                |
| `last_pdl`   | float | 1.1022             | ✅        | Prior Day Low                 |

---

## 3. Pattern Features (Stage 1.2)

| Key                   | Type | Example              | Required             | Description                  |
| --------------------- | ---- | -------------------- | -------------------- | ---------------------------- |
| `candlestick_pattern` | str  | "bullish_engulfing" | ❌ (set by Stage 1.2) | Detected candlestick pattern |
| `pattern_location_sr` | bool | True                 | ❌ (set by Stage 1.2) | Whether pattern is near S/R  |

---

## 4. Confirmation Features (Stage 1.3)

| Key                 | Type  | Example                                        | Required | Description                                   |
| ------------------- | ----- | ---------------------------------------------- | -------- | --------------------------------------------- |
| `confirmation_bars` | list  | `[{"open":..., "close":..., "ema8":...}, ...]` | ✅        | Bars after the pattern                        |
| `trigger_price`     | float | 1.1060                                         | ✅        | Breakout trigger level based on pattern logic |

---

## 5. Indicator Confluence Features (Stage 1.4)

| Key          | Type  | Example | Required | Description            |
| ------------ | ----- | ------- | -------- | ---------------------- |
| `rsi14`      | float | 48.5    | ❌        | Current RSI(14) value  |
| `rsi14_prev` | float | 46.0    | ❌        | Previous RSI(14) value |
| `ema20`      | float | 1.1048  | ❌        | EMA 20                 |
| `ema50`      | float | 1.1040  | ❌        | EMA 50                 |

---

## 6. Derived / Contextual Fields

| Key              | Type | Example           | Required | Description                          |
| ---------------- | ---- | ----------------- | -------- | ------------------------------------ |
| `direction`      | str  | "LONG" or "SHORT" | ❌        | Direction bias from pattern/trend    |
| `volume_support` | bool | True              | ❌        | Stage 1.1 result reused in Stage 1.4 |

---

## Notes

* Agents 012/013 must ensure all **Required** fields are populated before passing to Agent 010.
* Optional fields may be None or omitted, but will disable certain rules/bonuses.
* All prices should be floats, in the instrument’s native precision.
* `candles` and `confirmation_bars` must be ordered oldest → newest.

---

## Agent 011 – ML Integration & Composite Score

*Last updated: 14-Aug-2025*

### Inputs from Agent 010 (no duplication)
* Agent 011 directly consumes all features defined in Sections 1–6 above in the **exact order and scale** defined by Agent 010.
* Rule output consumed: `final_decision` ("LONG" | "SHORT" | "NO_TRADE"), `rule_confidence_score` (**0–100**).

### New ML Output Fields (persisted on `TradeAnalysis`)
| Field                  | Type  | Scale / Example                              | Description                                        |
| ---------------------- | ----- | -------------------------------------------- | -------------------------------------------------- |
| `ml_signal`            | str   | Enum: "LONG" / "SHORT" / "NO_TRADE"          | ML-predicted action                                |
| `ml_prob_long`         | float | **0–1** (e.g., 0.72)                          | Probability of LONG                                |
| `ml_prob_short`        | float | **0–1** (e.g., 0.18)                          | Probability of SHORT                               |
| `ml_prob_no_trade`     | float | **0–1** (e.g., 0.10)                          | Probability of NO_TRADE                            |
| `composite_score`      | float | **0–100** (e.g., 81.0)                        | Final blended score (rule + ML), canonical 0–100   |
| `ml_model_version`     | str   | e.g., "v1.2.0"                                | Semantic model version used                        |
| `ml_model_hash_prefix` | str   | first 8–12 chars of SHA256                    | Model file provenance                              |
| `feature_importances`  | JSON  | list of objects (see format below)            | Top‑N most important features                      |

### Composite Score – Canonical 0–100 Scale

**Storage & scales**
- `composite_score` is stored in the DB as **0–100**.
- ML probabilities are stored raw as **0–1**, but the **selected** probability is converted to **0–100** before blending.
- `rule_confidence_score` is expected as **0–100** from Agent 010. (If any upstream emits 0–1, convert to 0–100 before blending.)

**Computation**
```python
if ml_signal == "NO_TRADE":
    # default behavior: treat ML confidence as 0 for composite
    ml_confidence_pct = 0.0
    # optional alternative (behind config flag only): use next-highest of {ml_prob_long, ml_prob_short} * 100
else:
    ml_confidence_pct = max(ml_prob_long, ml_prob_short) * 100.0  # convert 0–1 → 0–100

# Blend (all values in 0–100)
composite_score = clamp(
    (rule_confidence_score * (1.0 - ml_weight)) + (ml_confidence_pct * ml_weight),
    0.0,
    100.0,
)
```
- `ml_weight` fetched via `get_ml_weight_for_user()` with fallback to `DEFAULT_ML_WEIGHT`.
- `clamp()` ensures the result stays within **0–100**.

### Gating & Idempotency
- **Gating**: Skip ML execution if `final_decision == "NO_TRADE"` **or** `rule_confidence_score < MIN_RULE_CONF_FOR_ML`.
- **Idempotency**: If ML fields are already populated for the same `ml_model_version`/`ml_model_hash_prefix` and no `reprocess=True`, skip writes.

### Fallback Behavior (explicit)
- On ML load/predict failure (or missing features):
  - Leave `ml_*` fields **NULL**.
  - Set `composite_score = rule_confidence_score` (**copy the 0–100 rule score**), guaranteeing a single confidence field for downstream consumers.

### Feature Importances Format (compact, object form)
Persist a compact list of objects (magnitude only):
```json
[
  {"feature": "rsi14", "importance": 0.15},
  {"feature": "atr", "importance": 0.12},
  {"feature": "ema50", "importance": 0.10}
]
```
- Extracted via `ml_pipeline/explain.py#get_top_n_feature_importances()`.
- Order: descending by absolute importance. N controlled by config.

### Version / Hash Tracking
- Set both `ml_model_version` and `ml_model_hash_prefix` on any successful ML write.
- These fields enable audit reproducibility and model‑to‑decision traceability.

---

**End of Agent 011 Section**
