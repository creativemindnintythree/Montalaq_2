#!/usr/bin/env python
"""
C:\Users\AHMED AL BALUSHI\Montalaq_2\pipeline_tester_011.py

End-to-end test runner for Agent 011:
fetch (via Agent 013/012 pipeline hook) → rule (Agent 010 output already persisted)
→ ML (model singleton) → composite → DB update → one-line summary.

Notes
-----
• This script is safe to run locally; it uses Django ORM directly.
• By default it runs synchronously (no Celery worker needed) by importing the task
  function body from celery_tasks.run_ml_on_new_data and calling it directly.
• Idempotency rules in Agent 011’s task will be respected (no duplicate writes).

Usage
-----
python pipeline_tester_011.py --symbol EURUSD --timeframe 1H --user 1
python pipeline_tester_011.py --trade-analysis-id 1234 --reprocess
python pipeline_tester_011.py --list-latest 10

Environment
-----------
Set DJANGO_SETTINGS_MODULE if your settings module is not the default:
  set DJANGO_SETTINGS_MODULE=montalaq_project.settings

Exit Codes
----------
0 = success (processed or intentionally gated)
2 = input/selection error
3 = runtime error (exception)
"""
from __future__ import annotations
import argparse
import json
import os
import sys
from datetime import datetime, timezone

# Ensure Django is ready
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "montalaq_project.settings")

try:
    import django  # type: ignore
    django.setup()
except Exception as e:  # pragma: no cover
    print(f"[ERR] Django setup failed: {e}")
    sys.exit(3)

from django.db import transaction
from django.utils.timezone import now

# ---- Project imports (exist in Agent 011 plan) ----
try:
    from ml_pipeline.config import (
        MIN_RULE_CONF_FOR_ML,
        DEFAULT_ML_WEIGHT,
        SIGNAL_LONG,
        SIGNAL_SHORT,
        SIGNAL_NO_TRADE,
    )
    from celery_tasks.run_ml_on_new_data import run_ml_on_new_data  # function, not .delay
    from backend.models import TradeAnalysis
except Exception as e:  # pragma: no cover
    print(f"[ERR] Import failure: {e}")
    sys.exit(3)


def pick_latest_ta(symbol: str, timeframe: str) -> TradeAnalysis | None:
    """Pick the most recent TradeAnalysis row produced by Agent 010 for a given symbol/timeframe
    that has a rule confidence and final_decision present.
    """
    qs = (
        TradeAnalysis.objects.filter(symbol=symbol, timeframe=timeframe)
        .exclude(final_decision__isnull=True)
        .exclude(rule_confidence_score__isnull=True)
        .order_by("-timestamp")
    )
    return qs.first()


def list_latest(limit: int = 10) -> None:
    rows = (
        TradeAnalysis.objects.exclude(final_decision__isnull=True)
        .exclude(rule_confidence_score__isnull=True)
        .order_by("-timestamp")[:limit]
    )
    for r in rows:
        print(
            f"id={r.id} {r.symbol}/{r.timeframe} ts={r.timestamp.isoformat()} "
            f"rule={r.rule_confidence_score} dec={r.final_decision} comp={r.composite_score}"
        )


def summarize(row: TradeAnalysis) -> str:
    def pct(x):
        return "-" if x is None else f"{x*100:.2f}%"

    feat = row.feature_importances or []
    feat_str = ", ".join([
        f"{d.get('feature','?')}:{d.get('importance',0):.3f}" for d in feat
    ])
    return (
        f"011 OK: id={row.id} {row.symbol}/{row.timeframe} ts={row.timestamp.isoformat()} "
        f"rule={row.rule_confidence_score:.1f} ml={row.ml_signal or '-'} "
        f"p_long={pct(row.ml_prob_long)} p_short={pct(row.ml_prob_short)} p_no={pct(row.ml_prob_no_trade)} "
        f"comp={row.composite_score:.1f} ver={row.ml_model_version or '-'}@{row.ml_model_hash_prefix or '-'} "
        f"TopN=[{feat_str}]"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Agent 011 pipeline tester")
    sel = parser.add_mutually_exclusive_group()
    sel.add_argument("--trade-analysis-id", type=int, help="Existing TradeAnalysis ID to process")
    sel.add_argument("--symbol", type=str, help="Symbol, e.g. EURUSD")
    parser.add_argument("--timeframe", type=str, help="Timeframe, e.g. 1H/15M/4H")
    parser.add_argument("--user", type=int, default=None, help="User ID (for prefs lookup)")
    parser.add_argument("--reprocess", action="store_true", help="Force re-run even if already processed for same model version")
    parser.add_argument("--list-latest", type=int, default=None, help="List latest N TA rows (rule-present) and exit")
    args = parser.parse_args()

    if args.list_latest:
        list_latest(args.list_latest)
        return 0

    ta: TradeAnalysis | None = None

    if args.trade_analysis_id:
        try:
            ta = TradeAnalysis.objects.get(id=args.trade_analysis_id)
        except TradeAnalysis.DoesNotExist:
            print(f"[ERR] TradeAnalysis id={args.trade_analysis_id} not found")
            return 2
    else:
        if not (args.symbol and args.timeframe):
            print("[ERR] Provide --trade-analysis-id OR (--symbol and --timeframe)")
            return 2
        ta = pick_latest_ta(args.symbol, args.timeframe)
        if not ta:
            print(f"[ERR] No TradeAnalysis rows with rule results found for {args.symbol}/{args.timeframe}")
            return 2

    # Gate visibility before calling the task (informative only; task will also gate)
    if (ta.final_decision == SIGNAL_NO_TRADE) or (
        (ta.rule_confidence_score or 0) < MIN_RULE_CONF_FOR_ML
    ):
        print(
            f"011 GATE: skipped id={ta.id} dec={ta.final_decision} "
            f"rule={ta.rule_confidence_score} rc_min={MIN_RULE_CONF_FOR_ML}"
        )
        return 0

    try:
        # Call synchronously; do not .delay to keep this a local tester
        run_ml_on_new_data(trade_analysis_id=ta.id, reprocess=args.reprocess, user_id=args.user)

        # Reload row and print one-line summary
        ta_refreshed = TradeAnalysis.objects.get(id=ta.id)
        print(summarize(ta_refreshed))
        return 0
    except Exception as e:  # pragma: no cover
        print(f"011 ERR: id={ta.id} details={e}")
        return 3


if __name__ == "__main__":
    sys.exit(main())
