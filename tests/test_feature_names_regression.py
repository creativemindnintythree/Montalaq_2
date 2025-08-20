# tests/test_feature_names_regression.py
import pytest

pytestmark = [pytest.mark.django_db]

def test_model_feature_vector_alignment():
    """
    If the loaded model exposes a 23-name feature set,
    ensure our vector builder returns a 23-float vector without crashing.
    """
    from ml_pipeline import ml_model
    from ml_pipeline.feature_builder import to_vector_by_feature_names, log_unknowns_once
    from backend.models import MarketData, MarketDataFeatures, TradeAnalysis
    from django.utils import timezone

    m = ml_model.get()
    bn = getattr(m, "booster_", None)
    names = list(bn.feature_name()) if (bn and hasattr(bn, "feature_name")) else list(getattr(m, "feature_name", lambda: [])())

    if len(names) != 23:
        pytest.xfail(f"Model does not expose 23 features here (got {len(names)}); this test is a safeguard for v1 only.")

    # Minimal MD/MDF/TA to feed the vector builder
    md = MarketData.objects.create(
        symbol="EUR/USD",
        timestamp=timezone.now(),
        open=1.10, high=1.11, low=1.09, close=1.105, volume=1000
    )
    mdf = MarketDataFeatures.objects.create(
        market_data=md,
        atr_14=0.0015, ema_8=1.104, ema_20=1.102, ema_50=1.095,
        rsi_14=55, bb_bandwidth=0.012,
    )
    ta = TradeAnalysis.objects.create(market_data_feature=mdf, timestamp=timezone.now())

    vec = to_vector_by_feature_names(ta, names)
    assert len(vec) == 23
    assert all(isinstance(x, (int, float)) for x in vec)

    # Should only log once; importantly it must not raise
    log_unknowns_once(names, getattr(ta, "market_data_feature", None))
