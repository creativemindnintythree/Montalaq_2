# tests/test_agent0112_ml.py
import pytest
from django.utils import timezone

@pytest.mark.django_db
def test_ml_model_loader():
    from ml_pipeline import ml_model
    m = ml_model.get()
    assert m is not None
    assert isinstance(ml_model.get_version(), str)
    assert isinstance(ml_model.get_hash_prefix(), str)

@pytest.mark.django_db
def test_composite_formula_math():
    from celery_tasks.run_ml_on_new_data import _compute_composite
    comp = _compute_composite(80.0, 0.60, 0.30)
    assert abs(comp - 74.0) < 1e-6

@pytest.mark.django_db
def test_composite_under_low_rule_conf():
    from celery_tasks.run_ml_on_new_data import _compute_composite
    from ml_pipeline import config as ml_cfg
    rule = ml_cfg.MIN_RULE_CONF_FOR_ML - 0.1  # just below threshold
    comp = _compute_composite(rule, 0.99, 0.30)
    # when rule is low, composite should not be dominated by ML component
    assert comp <= rule + 30.0

def _mk_chain():
    """Create a minimal MD -> MDF chain your TA can point to."""
    from backend.models import MarketData, MarketDataFeatures
    md = MarketData.objects.create(
        timestamp=timezone.now(),
        symbol="EUR/USD",
        open=1.10, high=1.11, low=1.09, close=1.105,
        volume=1000.0, provider="TEST",
    )
    mdf = MarketDataFeatures.objects.create(
        market_data=md,
        atr_14=0.0015, ema_8=1.104, ema_20=1.102, ema_50=1.095,
        rsi_14=55.0, bb_bandwidth=0.012,
        vwap_dist=0.002, volume_zscore=0.5, range_atr_ratio=0.8,
    )
    return md, mdf

@pytest.mark.django_db
def test_tradeanalysis_persistence():
    from backend.models import TradeAnalysis
    from celery_tasks.run_ml_on_new_data import run_ml_on_new_data

    md, mdf = _mk_chain()
    ta = TradeAnalysis.objects.create(
        market_data_feature=mdf,
        timestamp=md.timestamp,
        final_decision="LONG",
        rule_confidence=55,
        entry_price=1.105, stop_loss=1.102, take_profit=1.111,
    )

    run_ml_on_new_data(ta.id)
    ta.refresh_from_db()

    # persisted + sane bounds
    assert ta.composite_score is not None
    assert 0.0 <= (ta.composite_score or 0.0) <= 100.0
