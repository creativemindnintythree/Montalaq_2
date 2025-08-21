from django.core.management.base import BaseCommand
from backend.tasks.scheduler import tick

class Command(BaseCommand):
    help = "Run one full tick: ingest → (fresh) analyze for all pairs/TFs."

    def handle(self, *args, **options):
        # call task function directly (sync)
        tick()
        self.stdout.write(self.style.SUCCESS("Tick cycle complete."))
