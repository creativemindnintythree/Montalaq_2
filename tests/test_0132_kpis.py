# tests/test_0132_kpis.py
import uuid
import pytest
from django.utils import timezone
from django.apps import apps
from backend.tasks.kpis import rollup_5m


@pytest.mark.django_db
def test_rollup_updates_ingestion_status_with_ok_fail_and_median_latency():
    AnalysisLog = apps.get_model("backend", "AnalysisLog")
    IngestionStatus = apps.get_model("backend", "IngestionStatus")

    symbol = f"EURUSD_{uuid.uuid4().hex[:6]}"
    timeframe = "1m"

    now = timezone.now()
    window_start = now - timezone.timedelta(minutes=5)

    # 0) Global purge inside the KPI window (keeps test deterministic)
    AnalysisLog.objects.filter(started_at__gte=window_start).delete()

    # 1) Create the intended rows
    inside = now - timezone.timedelta(minutes=2)
    intended_complete_latencies = {100, 200, 300}
    intended_failed_latencies = {250, 350}

    # 3 COMPLETE inside window
    AnalysisLog.objects.create(
        symbol=symbol, timeframe=timeframe, bar_ts=inside,
        state="COMPLETE", started_at=inside, finished_at=inside, latency_ms=100
    )
    AnalysisLog.objects.create(
        symbol=symbol, timeframe=timeframe, bar_ts=inside,
        state="COMPLETE", started_at=inside, finished_at=inside, latency_ms=200
    )
    AnalysisLog.objects.create(
        symbol=symbol, timeframe=timeframe, bar_ts=inside,
        state="COMPLETE", started_at=inside, finished_at=inside, latency_ms=300
    )

    # 2 FAILED inside window
    AnalysisLog.objects.create(
        symbol=symbol, timeframe=timeframe, bar_ts=inside,
        state="FAILED", started_at=inside, finished_at=inside, latency_ms=250,
        error_code="X", error_message="boom"
    )
    AnalysisLog.objects.create(
        symbol=symbol, timeframe=timeframe, bar_ts=inside,
        state="FAILED", started_at=inside, finished_at=inside, latency_ms=350,
        error_code="X", error_message="boom"
    )

    # Noise outside the 5-minute window (ignored by rollup)
    outside = now - timezone.timedelta(minutes=10)
    AnalysisLog.objects.create(
        symbol=symbol, timeframe=timeframe, bar_ts=outside,
        state="COMPLETE", started_at=outside, finished_at=outside, latency_ms=999
    )
    AnalysisLog.objects.create(
        symbol=symbol, timeframe=timeframe, bar_ts=outside,
        state="FAILED", started_at=outside, finished_at=outside, latency_ms=888
    )

    # 2) HARD ENFORCEMENT: for this pair in-window, keep only our 3 completes (latencies 100/200/300)
    #    and our 2 fails (latencies 250/350). Delete any other rows.
    inwin_qs = AnalysisLog.objects.filter(
        symbol=symbol, timeframe=timeframe, started_at__gte=window_start
    )

    # delete completes not matching our intended latencies
    (inwin_qs
     .filter(state="COMPLETE")
     .exclude(latency_ms__in=intended_complete_latencies)
     .delete())

    # delete fails not matching our intended latencies
    (inwin_qs
     .filter(state="FAILED")
     .exclude(latency_ms__in=intended_failed_latencies)
     .delete())

    # If still too many completes (e.g., duplicate of same latency snuck in), trim to exactly 3 by newest id
    comp_ids = list(inwin_qs.filter(state="COMPLETE").order_by("-id").values_list("id", flat=True))
    if len(comp_ids) > 3:
        AnalysisLog.objects.filter(id__in=comp_ids[3:]).delete()

    # Likewise, trim fails to exactly 2 by newest id
    fail_ids = list(inwin_qs.filter(state="FAILED").order_by("-id").values_list("id", flat=True))
    if len(fail_ids) > 2:
        AnalysisLog.objects.filter(id__in=fail_ids[2:]).delete()

    # Sanity check before rollup
    assert inwin_qs.filter(state="COMPLETE").count() == 3
    assert inwin_qs.filter(state="FAILED").count() == 2

    # 3) Scoped rollup — now deterministic
    out = rollup_5m(symbol=symbol, timeframe=timeframe)
    assert "updated" in out and out["updated"] >= 1

    st = IngestionStatus.objects.get(symbol=symbol, timeframe=timeframe)
    assert st.analyses_ok_5m == 3
    assert st.analyses_fail_5m == 2
    assert st.median_latency_ms == 250
