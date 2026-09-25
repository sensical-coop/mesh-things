import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("registry", "0006_owner_alarm_email_cooldown"),
    ]

    operations = [
        migrations.AddField(
            model_name="mesh",
            name="is_public",
            field=models.BooleanField(default=False),
        ),
        migrations.CreateModel(
            name="MeshViewer",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "mesh",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="viewer_grants",
                        to="registry.mesh",
                    ),
                ),
                (
                    "viewer",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="mesh_view_grants",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"db_table": "mesh_viewers"},
        ),
        migrations.AddConstraint(
            model_name="meshviewer",
            constraint=models.UniqueConstraint(fields=("mesh", "viewer"), name="uq_mesh_viewer"),
        ),
    ]
