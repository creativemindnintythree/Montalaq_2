# Agent 011 Handoff – Machine Learning Integration & Composite Score

## Purpose

This document explains the logic, constants, idempotency rules, and logging format for Agent 011's Machine Learning (ML) integration in the Montalaq\_2 pipeline.

---

## 1. Formula for Composite Score

The composite score blends the **Rule Engine Confidence** and the **ML Model Probability**:

$$
\text{Composite} = (\text{Rule Confidence} \times (1 - w)) + (\text{ML Probability} \times w)
$$

* **Rule Confidence**: Float (0.0–1.0) output from Agent 010's rule engine.
* **ML Probability**: Probability of correct signal predicted by ML model (0.0–1.0).
* **w (ml\_weight)**: ML weight factor, default **0.30** (30%).

  * User-specific overrides retrieved via `get_ml_weight_for_user(user_id)`.
  * If no preference, fallback to `DEFAULT_ML_WEIGHT` constant.

Example:

> Rule Confidence = 0.80, ML Probability = 0.60, w = 0.30 → Composite = 0.74

---

## 2. Scaling Rules

* Both **Rule Confidence** and **ML Probability** must be normalized to **0.0–1.0** before applying the formula.
* If Rule Confidence is stored as a percentage (0–100), divide by 100 before blending.
* Store **Composite Score** in DB as float (0.0–1.0).

---

## 3. Gating Constants

* **MIN\_RULE\_CONF\_FOR\_ML**: ML step only runs if `rule_confidence_score >= MIN_RULE_CONF_FOR_ML`.

  * Default = **0.50** (50%).
* **NO\_TRADE skip**: ML step skipped entirely if `final_decision == "NO_TRADE"`.

This ensures ML is used as a **confirmation filter**, not a standalone signal.

---

## 4. Idempotency Rules

* **TradeAnalysis row** is updated in-place.
* If ML fields (`ml_signal`, `ml_prob_long`, etc.) are already populated for this row, **skip re-running ML** unless explicitly forced.
* Use **ml\_model\_hash\_prefix** to detect changes in the model file:

  * If hash differs from stored value → allow re-run.

---

## 5. Failure Handling

* **Soft Fail**: If ML prediction fails, log error with `011 ERR` and leave ML fields null.
* **Hard Fail**: If data is missing or corrupted → abort task with `retry()`.
* Never block downstream processes; failure in ML step should not crash the whole pipeline.

---

## 6. Logging Format

Logs should clearly indicate gating, success, idempotency, or errors:

| Tag         | Meaning                                                 |
| ----------- | ------------------------------------------------------- |
| `011 GATE`  | ML skipped due to gating (NO\_TRADE or low confidence). |
| `011 OK`    | ML executed and results stored.                         |
| `011 IDEMP` | ML skipped due to idempotency.                          |
| `011 ERR`   | Error in ML execution.                                  |

Example log sequence:

```
[011 GATE] Trade 1234 skipped ML – NO_TRADE
[011 OK] Trade 5678 ML done: signal=LONG, composite=0.74
[011 IDEMP] Trade 91011 already processed – skipping ML
[011 ERR] Trade 121314 ML failed – ValueError: ...
```

---

## 7. Persisted Fields in `TradeAnalysis`

Agent 011 writes/updates these fields:

* `ml_signal`: CharField, predicted trade direction.
* `ml_prob_long`, `ml_prob_short`, `ml_prob_no_trade`: Float probabilities.
* `composite_score`: Float blended confidence.
* `ml_model_version`: Version string of the model used.
* `ml_model_hash_prefix`: First 12 chars of model file hash.
* `feature_importances`: JSON list of `{feature, importance}` pairs from `get_top_n_feature_importances()`.

---

## 8. Testing & Verification

* **Unit tests**: Simulate `TradeAnalysis` rows with varying rule outcomes to verify gating.
* **Integration test**: Use `pipeline_tester_011.py` to simulate full run from rules → ML → composite.
* Validate:

  * Composite formula correctness.
  * Gating works as expected.
  * Logs match the format.
  * Fields persist correctly in DB.

---

**End of Document**
