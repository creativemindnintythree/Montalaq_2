from django.db import migrations

class Migration(migrations.Migration):
    dependencies = [
        ("backend", "0012_remove_tradeanalysis_backend_tra_timesta_a54992_idx_and_more"),
    ]

    operations = [
        # Temporarily drop the unique_together so backfill can set duplicates if they exist.
        migrations.AlterUniqueTogether(
            name="tradeanalysis",
            unique_together=set(),
        ),
    ]
