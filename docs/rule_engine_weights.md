# Rule Engine Weights – Stage 1.1 to 1.4

This document defines the official scoring weights and thresholds for **Agent 010’s rule-based engine**, covering Stage 1.1 through Stage 1.4. These values are centralized in `trading/rules/constants.py` and must be updated in both the code and this document if changed.

---

## 1. Overview

The rule engine assigns **points** to each stage based on the detected market conditions. These points are multiplied by predefined **stage weights** to compute a normalized confidence score between **0 and 100**.

If any **red-flag rule** is triggered, the engine will force `final_decision = NO_TRADE` regardless of the total score.

---

## 2. Stage Weights & Criteria

| Stage | Description                                   | Max Points | Weight (%) | Criteria Summary                                                                                      |
| ----- | --------------------------------------------- | ---------- | ---------- | ----------------------------------------------------------------------------------------------------- |
| 1.1   | **Context** – Volume support, proximity to SR | 30         | 30%        | Checks if current close is near significant Support/Resistance and if volume is above average.        |
| 1.2   | **Pattern** – Candlestick / Chart Patterns    | 30         | 30%        | Detects bullish/bearish patterns, confirms location relevance (SR proximity). Red-flag if none found. |
| 1.3   | **Confirmation** – Indicator alignment        | 20         | 20%        | Confirms pattern bias with indicators (e.g., RSI, MACD, MA crossovers).                               |
| 1.4   | **Confluence** – Multi-factor agreement       | 20         | 20%        | Strategy-specific confluence checks (RSI+Volume, MA+SR, etc.).                                        |

---

## 3. Red-Flag Rules

If any of these occur, **decision = NO\_TRADE** regardless of score:

1. **No valid pattern detected** in Stage 1.2.
2. **ATR value is None or 0** (cannot calculate SL/TP).
3. **Volume extremely low** (below 20% of average volume for the last N bars).
4. **Major event filter** triggered (reserved for future).

---

## 4. Scoring Formula

```
confidence_score = (
    (stage_11_points / stage_11_max) * stage_11_weight +
    (stage_12_points / stage_12_max) * stage_12_weight +
    (stage_13_points / stage_13_max) * stage_13_weight +
    (stage_14_points / stage_14_max) * stage_14_weight
) * 100
```

---

## 5. Example Calculation

* Stage 1.1 → 20 / 30 points (66.67%) × 30% = **20.0**
* Stage 1.2 → 30 / 30 points (100%) × 30% = **30.0**
* Stage 1.3 → 15 / 20 points (75%) × 20% = **15.0**
* Stage 1.4 → 10 / 20 points (50%) × 20% = **10.0**

**Total Confidence = 75.0%**

If Stage 1.2 failed (no pattern) → **Red-flag → NO\_TRADE**.

---

## 6. Reference – constants.py Mapping

```
STAGE_11_WEIGHT = 0.30
STAGE_12_WEIGHT = 0.30
STAGE_13_WEIGHT = 0.20
STAGE_14_WEIGHT = 0.20

MAX_POINTS_STAGE_11 = 30
MAX_POINTS_STAGE_12 = 30
MAX_POINTS_STAGE_13 = 20
MAX_POINTS_STAGE_14 = 20

RED_FLAG_NO_PATTERN = True
VOLUME_LOW_THRESHOLD = 0.2
```

---

**Maintainer:** Agent 010 – Rule-Based Analysis Engine Lead
