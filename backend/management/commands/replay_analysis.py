from django.core.management.base import BaseCommand
from django.apps import apps

class Command(BaseCommand):
    help = "Re-run analysis deterministically over stored MarketData for a pair/timeframe."

    def add_arguments(self, p):
        p.add_argument("--pair", required=True)
        p.add_argument("--tf", required=True)

    def handle(self, *args, **o):
        MarketData = apps.get_model("backend","MarketData")
        MarketDataFeatures = apps.get_model("backend","MarketDataFeatures")
        TradeAnalysis = apps.get_model("backend","TradeAnalysis")
        from backend.tasks.analysis_tasks import analyze_latest

        qs = (MarketData.objects
              .filter(symbol=o["pair"], timeframe=o["tf"])
              .order_by("timestamp")
              .values_list("timestamp", flat=True))
        count = 0
        for _ in qs:
            # ensure features row exists for each bar
            md = (MarketData.objects
                  .filter(symbol=o["pair"], timeframe=o["tf"])
                  .order_by("-timestamp").first())
            if not md:
                continue
            MarketDataFeatures.objects.get_or_create(market_data=md)
            analyze_latest(o["pair"], o["tf"])   # call sync; Celery not required
            count += 1
        self.stdout.write(self.style.SUCCESS(f"Replay complete: {count} analyses attempted."))
