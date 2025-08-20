# SL/TP Methodology

## Overview
This document describes the Stop Loss (SL) and Take Profit (TP) calculation methodology implemented in:
```
C:\Users\AHMED AL BALUSHI\Montalaq_2\trading\rules\execution.py
```

The method is designed for consistency across all trade evaluations performed by the Rule Engine.

---

## Inputs Required
- **close** *(float)*: Latest closing price.
- **atr** *(float)*: Average True Range value (currently 14-period by default).
- **direction** *(str)*: "LONG" or "SHORT" — decision from the Rule Engine.
- **ATR_MULTIPLIER_SL** *(float)*: Multiplier applied to ATR for SL distance.
- **DEFAULT_RR_RATIO** *(float)*: Default Risk:Reward ratio for TP calculation.

---

## Calculation Steps

1. **Validation**
   - Ensure both `close` and `atr` are provided.
   - If either is `None` or zero, skip SL/TP calculation.

2. **Stop Loss (SL)**
   - **LONG**: `SL = close - (ATR_MULTIPLIER_SL * atr)`
   - **SHORT**: `SL = close + (ATR_MULTIPLIER_SL * atr)`

3. **Take Profit (TP)**
   - Distance from entry to SL is multiplied by `DEFAULT_RR_RATIO`.
   - **LONG**: `TP = close + (distance_to_SL * DEFAULT_RR_RATIO)`
   - **SHORT**: `TP = close - (distance_to_SL * DEFAULT_RR_RATIO)`

4. **R:R Ratio**
   - The returned value includes the risk:reward ratio used for the TP projection.

---

## Example
```
close = 1.2000
atr = 0.0012
ATR_MULTIPLIER_SL = 1.5
DEFAULT_RR_RATIO = 2.0

# For LONG:
SL = 1.2000 - (1.5 * 0.0012) = 1.1982
TP = 1.2000 + ((1.2000 - 1.1982) * 2.0) = 1.2036
```

---

## Future-Proofing
- Structure-based SL/TP: Placeholder hook exists in `execution.py` for future enhancement using structural support/resistance.
- Configurable multipliers: All constants are stored in `constants.py` for easy adjustment without code changes.

---

**File Location:**
```
C:\Users\AHMED AL BALUSHI\Montalaq_2\docs\sl_tp_methodology.md
