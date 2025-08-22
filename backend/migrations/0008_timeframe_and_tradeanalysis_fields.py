# backend/migrations/0008_timeframe_and_tradeanalysis_fields.py
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('backend', '0007_rename_rule_confidence_score'),  # keep your actual previous file here
    ]

    operations = [
        # --- MarketData: add timeframe and set unique_together (symbol,timeframe,timestamp)
        migrations.AddField(
            model_name='marketdata',
            name='timeframe',
            field=models.CharField(max_length=8, default='1h', db_index=True),
            preserve_default=True,   # default stays to backfill existing rows
        ),
        migrations.AlterUniqueTogether(
            name='marketdata',
            unique_together={('symbol', 'timeframe', 'timestamp')},
        ),
        migrations.AddIndex(
            model_name='marketdata',
            index=models.Index(
                fields=['symbol', 'timeframe', 'timestamp'],
                name='md_symtf_ts_idx',
            ),
        ),

        # --- TradeAnalysis: enforce idempotence per bar via (market_data_feature, timestamp)
        # Do NOT reference nonexistent symbol/timeframe fields here.
        migrations.AlterUniqueTogether(
            name='tradeanalysis',
            unique_together={('market_data_feature', 'timestamp')},
        ),
        migrations.AddIndex(
            model_name='tradeanalysis',
            index=models.Index(
                fields=['market_data_feature', 'timestamp'],
                name='ta_mdf_ts_idx',
            ),
        ),
    ]
