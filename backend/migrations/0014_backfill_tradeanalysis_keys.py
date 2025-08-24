from django.db import migrations

def backfill_trade_keys(apps, schema_editor):
    TradeAnalysis = apps.get_model("backend", "TradeAnalysis")
    # Historical models: no select_related; iterate safely.
    batch = []
    BATCH_SIZE = 500

    for ta in TradeAnalysis.objects.all().iterator():
        mdf = getattr(ta, "market_data_feature", None)
        md = getattr(mdf, "market_data", None) if mdf else None

        if md:
            changed = False
            if getattr(ta, "symbol", None) is None:
                ta.symbol = md.symbol
                changed = True
            if getattr(ta, "timeframe", None) is None:
                ta.timeframe = md.timeframe
                changed = True
            if getattr(ta, "bar_ts", None) is None:
                ta.bar_ts = md.timestamp
                changed = True
            if changed:
                batch.append(ta)

            if len(batch) >= BATCH_SIZE:
                TradeAnalysis.objects.bulk_update(batch, ["symbol", "timeframe", "bar_ts"])
                batch.clear()

    if batch:
        TradeAnalysis.objects.bulk_update(batch, ["symbol", "timeframe", "bar_ts"])

class Migration(migrations.Migration):
    dependencies = [
        ("backend", "0013_relax_tradeanalysis_keys"),
    ]

    operations = [
        migrations.RunPython(backfill_trade_keys, migrations.RunPython.noop),
    ]
