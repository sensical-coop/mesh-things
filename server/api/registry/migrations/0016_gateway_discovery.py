from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('registry', '0015_owner_status_alerts'),
    ]

    operations = [
        migrations.AddField(
            model_name='mesh',
            name='discover_gateways',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='device',
            name='discovered_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
