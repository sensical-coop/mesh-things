from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("registry", "0016_gateway_discovery"),
    ]

    operations = [
        migrations.AddField(
            model_name="owner",
            name="source_rate_alerts_enabled",
            field=models.BooleanField(default=False),
        ),
    ]
