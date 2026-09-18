"""Give every payload_kind a namespace.

Only `telemetry:<variant>` had one. The measurement half is unchanged, so no
InfluxDB series moves and the quality-config keys, being channels, stay put.
"""
from django.db import migrations

from common.channels import COMPUTED, DEVICE

# Flat spelling -> namespaced spelling. Telemetry rows are already correct.
RENAMES = {
    "derived": f"{COMPUTED}:derived",
    "quality": f"{COMPUTED}:quality",
    "alarms": f"{COMPUTED}:alarms",
    "position": f"{DEVICE}:position",
    "nodeinfo": f"{DEVICE}:nodeinfo",
}


def _apply(apps, mapping):
    for model_name in ("MeasurementType", "TelemetryVariant"):
        model = apps.get_model("registry", model_name)
        for old, new in mapping.items():
            model.objects.filter(payload_kind=old).update(payload_kind=new)


def forwards(apps, schema_editor):
    _apply(apps, RENAMES)
    # Undecoded portnums were "portnum:<n>" while storage wrote "portnum_<n>",
    # so the two never matched. Rewrite to the spelling that does.
    model = apps.get_model("registry", "MeasurementType")
    for row in model.objects.filter(payload_kind__startswith="portnum:"):
        row.payload_kind = f"{DEVICE}:portnum_{row.payload_kind.split(':', 1)[1]}"
        row.save(update_fields=["payload_kind"])


def backwards(apps, schema_editor):
    _apply(apps, {new: old for old, new in RENAMES.items()})
    model = apps.get_model("registry", "MeasurementType")
    for row in model.objects.filter(payload_kind__startswith=f"{DEVICE}:portnum_"):
        row.payload_kind = f"portnum:{row.payload_kind.rsplit('_', 1)[1]}"
        row.save(update_fields=["payload_kind"])


class Migration(migrations.Migration):
    dependencies = [("registry", "0001_initial")]
    operations = [migrations.RunPython(forwards, backwards)]
