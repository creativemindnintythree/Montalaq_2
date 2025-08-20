# Django management command: run_ml_batch
# Usage:
#   python manage.py run_ml_batch --limit 20
# Optional flags:
#   --ids 1,2,3          # explicit TA ids to process (overrides limit)
#   --order newest|oldest # default newest
#   --dry-run             # build vectors / gate, but don't persist

from __future__ import annotations
from typing import List, Optional

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from backend.models import TradeAnalysis
from celery_tasks.run_ml_on_new_data import run_ml_on_new_data


class Command(BaseCommand):
    help = "Run Agent 011.2 ML pipeline over a batch of TradeAnalysis rows"

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=20,
            help="Max number of rows to process when --ids is not provided (default: 20)",
        )
        parser.add_argument(
            "--ids",
            type=str,
            default="",
            help="Comma-separated TradeAnalysis ids to process (overrides --limit)",
        )
        parser.add_argument(
            "--order",
            type=str,
            choices=["newest", "oldest"],
            default="newest",
            help="Order to scan rows when using --limit (default: newest)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Compute gating and vectors but skip persistence (log-only)",
        )

    def handle(self, *args, **options):
        ids_raw: str = options.get("ids") or ""
        limit: int = int(options.get("limit") or 20)
        order: str = options.get("order") or "newest"
        dry_run: bool = bool(options.get("dry_run") or False)

        # Choose queryset
        if ids_raw.strip():
            try:
                ids: List[int] = [int(x) for x in ids_raw.split(",") if x.strip()]
            except ValueError:
                raise CommandError("--ids must be a comma-separated list of integers")
            qs = TradeAnalysis.objects.filter(id__in=ids).order_by("id")
        else:
            qs = TradeAnalysis.objects.all()
            qs = qs.order_by("-id" if order == "newest" else "id")[:limit]

        total = qs.count()
        if total == 0:
            self.stdout.write(self.style.WARNING("No TradeAnalysis rows to process"))
            return

        self.stdout.write(self.style.NOTICE(
            f"Agent 011.2: running ML batch on {total} TradeAnalysis row(s)"
        ))

        processed = 0
        failures = 0

        for ta in qs:
            try:
                if dry_run:
                    # Wrap in a rollback-only transaction so nothing persists
                    with transaction.atomic():
                        run_ml_on_new_data(ta.id)
                        raise transaction.TransactionManagementError("dry-run: rollback")
                else:
                    run_ml_on_new_data(ta.id)
                processed += 1
                self.stdout.write(f"ok  ta_id={ta.id}")
            except transaction.TransactionManagementError:
                processed += 1
                self.stdout.write(f"ok(dry) ta_id={ta.id}")
            except Exception as e:
                failures += 1
                self.stderr.write(self.style.ERROR(f"fail ta_id={ta.id} error={e}"))

        summary = f"done processed={processed} failures={failures}"
        if failures:
            self.stdout.write(self.style.WARNING(summary))
        else:
            self.stdout.write(self.style.SUCCESS(summary))
