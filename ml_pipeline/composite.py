# ml_pipeline/composite.py
"""
Composite confidence calculator for Montalaq_2.

Inputs:
- rule_confidence: float in [0, 100]
- ml_probability: float in [0.0, 1.0]
- ml_weight: float in [0.0, 1.0]  (default 0.30)

Output:
- composite_score: float in [0, 100]

Rule: ML cannot overturn a NO_TRADE — only call this when the rule engine produced LONG/SHORT.
"""

from typing import Optional


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(value)))


def compute_composite(rule_confidence: float, ml_probability: float, ml_weight: float = 0.30) -> float:
    """
    Compute blended confidence on a 0–100 scale.

    composite = (1 - w) * rule_confidence + w * (ml_probability * 100)

    Raises:
        ValueError: if inputs are None or outside expected ranges.
    """
    if rule_confidence is None or ml_probability is None:
        raise ValueError("rule_confidence and ml_probability must be provided")

    # Normalize and validate inputs
    rc = float(rule_confidence)
    mp = float(ml_probability)
    w = _clamp(ml_weight, 0.0, 1.0)

    if not (0.0 <= rc <= 100.0):
        raise ValueError(f"rule_confidence out of range [0,100]: {rc}")
    if not (0.0 <= mp <= 1.0):
        raise ValueError(f"ml_probability out of range [0,1]: {mp}")

    composite = (1.0 - w) * rc + w * (mp * 100.0)
    return _clamp(composite, 0.0, 100.0)
