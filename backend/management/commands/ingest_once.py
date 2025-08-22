from django.core.management.base import BaseCommand
from backend.tasks.ingest_tasks import ingest_once

class Command(BaseCommand):
    help = "Run a single ingestion cycle (TEMP AllTick shim)."

    def handle(self, *args, **options):
        # call the task function directly (sync)
        ingest_once()
        self.stdout.write(self.style.SUCCESS("Ingestion cycle complete."))
