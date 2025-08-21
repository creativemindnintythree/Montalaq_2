# tests/test_agent0112_batch_task.py
import datetime as dt
import pytest
from django.utils import timezone

pytestmark = [pytest.mark.django_db]

def test_batch_enqueues_recent(settings, monkeypatch):
    """
    Verifies backend.tasks_ml_batch.batch_run_recent:
    - selects only recent TradeAnalysis rows (by timestamp)
    - calls run_ml_on_new_data once per selected row
    - returns processed count
    """
    # Run Celery tasks locally/synchronously
    settings.CELERY_TASK_ALWAYS_EAGER = True

    from backend.models import MarketData, MarketDataFeatures, TradeAnalysis

    # Create a dummy MD/ MDF to satisfy FK requirements
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

    # 3 rows: 2 are recent, 1 is old
    now = timezone.now()
    recent_1 = TradeAnalysis.objects.create(market_data_feature=mdf, timestamp=now - dt.timedelta(minutes=5))
    recent_2 = TradeAnalysis.objects.create(market_data_feature=mdf, timestamp=now - dt.timedelta(minutes=30))
    old_row   = TradeAnalysis.objects.create(market_data_feature=mdf, timestamp=now - dt.timedelta(hours=6))

    called_ids = []
    def _fake_run_ml_on_new_data(ta_id: int) -> None:
        called_ids.append(ta_id)
        # mimic the task not raising

    # Patch the real task function used by batch
    from backend import tasks_ml_batch
    monkeypatch.setattr(tasks_ml_batch, "run_ml_on_new_data", _fake_run_ml_on_new_data)

    # Run the batch with a 60‑minute lookback; should pick the 2 “recent” rows
    processed = tasks_ml_batch.batch_run_recent(limit=50, minutes=60)
    assert processed == 2
    assert set(called_ids) == {recent_1.id, recent_2.id}
    assert old_row.id not in called_ids
