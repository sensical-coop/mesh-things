"""Units and vocabulary for the channels a reading belongs to."""
from common.channels import channel_name
from registry.models import MeasurementType


def get_measurement_types() -> dict[str, dict]:
    """Returns {channel_name: {"unit", "quantity_kind", "vocabulary_uri"}}."""
    return {
        channel_name(row.payload_kind, row.field_name): {
            "unit": row.native_unit,
            "quantity_kind": row.quantity_kind,
            "vocabulary_uri": row.vocabulary_uri,
        }
        for row in MeasurementType.objects.all()
    }
