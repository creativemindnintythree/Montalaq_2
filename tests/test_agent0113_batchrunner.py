import logging
import pytest
from datetime import timedelta
from django.utils import timezone

from backend.models import MarketData, MarketDataFeatures, TradeAnalysis

# target under test
from backend.tasks_ml_batch import batch_run_recent


@pytest.mark.django_db
def _mk_ta(final_decision="LONG", minutes_ago=1):
    """Create a TradeAnalysis row with a timestamp minutes_ago in the past."""
    ts = timezone.now() - timedelta(minutes=minutes_ago)
    md = MarketData.objects.create(
        timestamp=ts,
        symbol="EURUSD",
        open=1.0, high=1.0, low=1.0, close=1.0, volume=1.0, provider="test",
    )
    mdf = MarketDataFeatures.objects.create(market_data=md)
    ta = TradeAnalysis.objects.create(
        market_data_feature=mdf,
        timestamp=ts,
        rule_confidence=60,
        final_decision=final_decision,
    )
    return ta


@pytest.mark.django_db
def test_batch_runner_mixed_eligibility_and_resilience(monkeypatch, caplog):
    """
    - Creates eligible + ineligible TA rows.
    - Patches run_ml_on_new_data to succeed for some, fail for one.
    - Asserts the batch processes only eligible rows and keeps running on failure.
    - Validates summary log line presence.
    """
    # In-window, eligible
    ta1 = _mk_ta("LONG", minutes_ago=2)
    ta2 = _mk_ta("SHORT", minutes_ago=3)
    ta3 = _mk_ta("LONG", minutes_ago=4)

    # In-window but ineligible (NO_TRADE)
    _mk_ta("NO_TRADE", minutes_ago=1)

    # Out-of-window (older than 15 minutes)
    _mk_ta("LONG", minutes_ago=30)

    # Patch the symbol imported inside backend.tasks_ml_batch
    calls = {"n": 0}

    def _fake_runner(ta_id):
        calls["n"] += 1
        # Fail exactly once (to verify resilience)
        if calls["n"] == 2:
            raise RuntimeError("synthetic failure for resilience test")
        # else succeed (no return needed)

    monkeypatch.setattr("backend.tasks_ml_batch.run_ml_on_new_data", _fake_runner, raising=True)

    # Capture logs from the module logger
    caplog.set_level(logging.INFO, logger="backend.tasks_ml_batch")

    processed = batch_run_recent(limit=50, minutes=15)

    # 3 eligible in window, 1 fails → processed count should be 2
    assert processed == 2

    # run_ml_on_new_data should have been invoked for each eligible row (3 calls)
    assert calls["n"] == 3

    # Summary log present
    summary_msgs = [r for r in caplog.records if "batch_run_recent processed=" in getattr(r, "msg", "")]
    assert summary_msgs, "Expected a summary log line from batch_run_recent"

    # Error log present for the synthetic failure
    error_msgs = [r for r in caplog.records if "failed TA=" in getattr(r, "msg", "")]
    assert error_msgs, "Expected an error log for the failed TA"
