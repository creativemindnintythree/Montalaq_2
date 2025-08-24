from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [
        ("backend", "0014_backfill_tradeanalysis_keys"),
    ]

    operations = [
        # Make keys non-null now that they’re backfilled.
        migrations.AlterField(
            model_name="tradeanalysis",
            name="symbol",
            field=models.CharField(max_length=20, db_index=True, null=False, blank=False),
        ),
        migrations.AlterField(
            model_name="tradeanalysis",
            name="timeframe",
            field=models.CharField(max_length=10, db_index=True, null=False, blank=False),
        ),
        migrations.AlterField(
            model_name="tradeanalysis",
            name="bar_ts",
            field=models.DateTimeField(db_index=True, null=False, blank=False),
        ),
        # Re‑add the uniqueness guarantee.
        migrations.AlterUniqueTogether(
            name="tradeanalysis",
            unique_together={("symbol", "timeframe", "bar_ts")},
        ),
    ]
