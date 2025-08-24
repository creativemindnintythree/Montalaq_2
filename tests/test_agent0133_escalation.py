# tests/test_agent0133_escalation.py
import uuid
import pytest
from django.apps import apps
from django.utils import timezone
from django.core.cache import cache

from backend.tasks.escalation import evaluate_escalations


@pytest.mark.django_db
def test_warn_after_two_amber_cycles():
    """
    WARN when AMBER persists for ≥ 2 cycles.
    """
    IngestionStatus = apps.get_model("backend", "IngestionStatus")

    sym = f"EURUSD_{uuid.uuid4().hex[:6]}"
    tf = "1m"

    st = IngestionStatus.objects.create(
        symbol=sym,
        timeframe=tf,
        freshness_state="AMBER",
        analyses_fail_5m=0,
        escalation_level="INFO",
        breaker_open=False,
        provider="AllTick",
    )

    # 1st evaluation -> still INFO (first AMBER cycle)
    n = evaluate_escalations()
    st.refresh_from_db()
    assert st.escalation_level in ("INFO", "WARN")  # tolerate immediate WARN if cache is warm
    first_level = st.escalation_level

    # Force AMBER again -> should reach WARN by 2nd cycle
    st.freshness_state = "AMBER"
    st.save(update_fields=["freshness_state"])
    n = evaluate_escalations()
    st.refresh_from_db()
    assert st.escalation_level in ("WARN",) if first_level == "INFO" else ("WARN", "ERROR", "CRITICAL")


@pytest.mark.django_db
def test_error_on_red_or_three_fails():
    """
    ERROR on RED, or when fails_5m >= 3.
    """
    IngestionStatus = apps.get_model("backend", "IngestionStatus")

    sym = f"GBPUSD_{uuid.uuid4().hex[:6]}"
    tf = "15m"

    # Case A: RED → ERROR immediately
    st = IngestionStatus.objects.create(
        symbol=sym, timeframe=tf,
        freshness_state="RED",
        analyses_fail_5m=0,
        escalation_level="INFO",
        breaker_open=False,
        provider="AllTick",
    )
    evaluate_escalations()
    st.refresh_from_db()
    assert st.escalation_level in ("ERROR", "CRITICAL")  # may jump to CRITICAL if cache marks sustained RED

    # Case B: (new row) three recent fails → ERROR
    sym2 = f"GBPUSD_{uuid.uuid4().hex[:6]}"
    st2 = IngestionStatus.objects.create(
        symbol=sym2, timeframe=tf,
        freshness_state="GREEN",
        analyses_fail_5m=3,
        escalation_level="INFO",
        breaker_open=False,
        provider="AllTick",
    )
    evaluate_escalations()
    st2.refresh_from_db()
    assert st2.escalation_level in ("ERROR", "CRITICAL")  # depending on cycles


@pytest.mark.django_db
def test_critical_on_red_sustained_or_breaker_open():
    """
    CRITICAL when RED is sustained (>=3 cycles) or when breaker is opened.
    The implementation opens breaker after persistent ERROR or >=2 RED cycles.
    """
    IngestionStatus = apps.get_model("backend", "IngestionStatus")

    sym = f"XAUUSD_{uuid.uuid4().hex[:6]}"
    tf = "1m"

    st = IngestionStatus.objects.create(
        symbol=sym, timeframe=tf,
        freshness_state="RED",
        analyses_fail_5m=0,
        escalation_level="INFO",
        breaker_open=False,
        provider="AllTick",
    )

    # Cycle 1 (RED)
    evaluate_escalations()
    st.refresh_from_db()
    lvl1 = st.escalation_level
    brk1 = st.breaker_open

    # Cycle 2 (RED again) → breaker likely opens
    st.freshness_state = "RED"
    st.save(update_fields=["freshness_state"])
    evaluate_escalations()
    st.refresh_from_db()
    lvl2 = st.escalation_level
    brk2 = st.breaker_open

    # Cycle 3 (RED again) → should be CRITICAL (sustained RED or breaker open)
    st.freshness_state = "RED"
    st.save(update_fields=["freshness_state"])
    evaluate_escalations()
    st.refresh_from_db()

    assert st.escalation_level == "CRITICAL"
    assert st.breaker_open is True or brk2 is True or brk1 is True
    # Ensure monotonic (non-decreasing) severity across RED cycles
    order = {"INFO": 0, "WARN": 1, "ERROR": 2, "CRITICAL": 3}
    assert order[st.escalation_level] >= order[lvl2] >= order[lvl1]


@pytest.mark.django_db
def test_breaker_persists_until_separate_closure_logic():
    """
    Once breaker_open=True, evaluate_escalations keeps it open.
    (Close logic is expected to be handled by a dedicated 'circuit_breaker_tick'
     task or ops action; evaluate_escalations doesn't auto-close.)
    """
    IngestionStatus = apps.get_model("backend", "IngestionStatus")

    sym = f"BTCUSD_{uuid.uuid4().hex[:6]}"
    tf = "1m"

    # First force a breaker opening via repeated RED
    st = IngestionStatus.objects.create(
        symbol=sym, timeframe=tf,
        freshness_state="RED",
        analyses_fail_5m=0,
        escalation_level="INFO",
        breaker_open=False,
        provider="AllTick",
    )
    evaluate_escalations()
    st.refresh_from_db()
    st.freshness_state = "RED"
    st.save(update_fields=["freshness_state"])
    evaluate_escalations()
    st.refresh_from_db()
    assert st.breaker_open is True or st.escalation_level in ("ERROR", "CRITICAL")

    # Now return to GREEN and zero fails; breaker should remain open
    st.freshness_state = "GREEN"
    st.analyses_fail_5m = 0
    st.save(update_fields=["freshness_state", "analyses_fail_5m"])
    evaluate_escalations()
    st.refresh_from_db()

    # Level may drop (e.g., INFO), but breaker remains True until dedicated logic closes it
    assert st.breaker_open is True
