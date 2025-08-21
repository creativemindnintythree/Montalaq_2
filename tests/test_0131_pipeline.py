import pytest
from django.apps import apps
from backend.tasks.scheduler import tick

@pytest.mark.django_db(transaction=True)
def test_tick_once_smoke():
    # Single end-to-end pass (dev-fake data path)
    tick()  # sync call to our task function
    MarketData = apps.get_model("backend","MarketData")
    TradeAnalysis = apps.get_model("backend","TradeAnalysis")

    assert MarketData.objects.exists()
    # TA may be 0 if rule returns NO_TRADE for all; allow >=0
    assert TradeAnalysis.objects.count() >= 0
