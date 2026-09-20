from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("registry", "0002_namespace_payload_kinds")]

    operations = [
        migrations.AddField(
            model_name="device",
            name="alarms_enabled",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="measurement",
            name="enabled_detectors",
            field=models.JSONField(blank=True, default=None, null=True),
        ),
        migrations.AddField(
            model_name="telemetryvariantmeasurement",
            name="default_enabled_detectors",
            field=models.JSONField(blank=True, default=list),
        ),
    ]
