from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("registry", "0004_range_per_device")]

    operations = [
        migrations.RenameField(
            model_name="device",
            old_name="alarms_enabled",
            new_name="absence_detection_enabled",
        ),
    ]
