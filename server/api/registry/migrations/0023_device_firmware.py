from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('registry', '0022_mesh_protocol_default_and_notice'),
    ]

    operations = [
        migrations.AddField(
            model_name='device',
            name='firmware_version',
            field=models.CharField(blank=True, max_length=32, null=True),
        ),
        migrations.AddField(
            model_name='device',
            name='region',
            field=models.CharField(blank=True, max_length=32, null=True),
        ),
        migrations.AddField(
            model_name='device',
            name='modem_preset',
            field=models.CharField(blank=True, max_length=32, null=True),
        ),
        migrations.AddField(
            model_name='device',
            name='firmware_seen_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
