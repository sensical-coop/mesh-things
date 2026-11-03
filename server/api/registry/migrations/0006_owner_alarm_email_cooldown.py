from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("registry", "0005_rename_alarms_enabled")]

    operations = [
        migrations.AddField(
            model_name="owner",
            name="alarm_email_cooldown_seconds",
            field=models.PositiveIntegerField(null=True, blank=True),
        ),
    ]
