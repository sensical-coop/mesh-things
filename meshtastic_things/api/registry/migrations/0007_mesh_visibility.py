from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("registry", "0006_owner_alarm_email_cooldown")]

    operations = [
        migrations.AddField(
            model_name="mesh",
            name="is_public",
            field=models.BooleanField(default=False),
        ),
    ]
