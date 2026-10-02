import uuid

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("registry", "0012_postprocessing_backfills"),
    ]

    operations = [
        migrations.AddField(
            model_name="device",
            name="archive_enabled",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="device",
            name="archive_enabled_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="device",
            name="archive_enabled_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.CreateModel(
            name="SinkInstruction",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("sink", models.CharField(max_length=64)),
                ("enabled", models.BooleanField()),
                ("mesh_id", models.UUIDField()),
                ("node_id", models.BigIntegerField()),
                ("given_by_name", models.CharField(max_length=255)),
                ("given_by_email", models.EmailField(max_length=254)),
                ("given_at", models.DateTimeField(default=django.utils.timezone.now)),
                (
                    "device",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="registry.device",
                    ),
                ),
                (
                    "given_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "sink_instructions",
            },
        ),
        migrations.AddIndex(
            model_name="sinkinstruction",
            index=models.Index(fields=["mesh_id", "node_id", "given_at"], name="sink_instr_mesh_node_at"),
        ),
    ]
