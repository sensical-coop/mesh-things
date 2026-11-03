from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [("registry", "0003_alarm_opt_in")]

    operations = [
        migrations.AddField(
            model_name="measurement",
            name="valid_min",
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="measurement",
            name="valid_max",
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.RemoveField(model_name="telemetryvariantmeasurement", name="valid_min"),
        migrations.RemoveField(model_name="telemetryvariantmeasurement", name="valid_max"),
    ]
