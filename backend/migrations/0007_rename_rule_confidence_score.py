from django.db import migrations

class Migration(migrations.Migration):

    dependencies = [
        ("backend", "0006_tradeanalysis_timestamp_and_more"),
    ]

    operations = [
        migrations.RenameField(
            model_name="tradeanalysis",
            old_name="rule_confidence_score",
            new_name="rule_confidence",
        ),
    ]
