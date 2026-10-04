"""Units and vocabulary for the channels a reading belongs to."""
from common.channels import channel_name
from registry.models import MeasurementType


def get_measurement_types() -> dict[str, dict]:
    """Returns {channel_name: catalog row}.
    """
    return {
        channel_name(row.payload_kind, row.field_name): {
            "payload_kind": row.payload_kind,
            "field_name": row.field_name,
            "description": row.description,
            "unit": row.native_unit,
            "quantity_kind": row.quantity_kind,
            "vocabulary_uri": row.vocabulary_uri,
        }
        for row in MeasurementType.objects.all()
    }
