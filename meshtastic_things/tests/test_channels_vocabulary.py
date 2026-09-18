"""payload_kind <-> measurement must round-trip for every family the writer emits."""
import pytest

from common.channels import (
    ORIGIN_COMPUTED,
    ORIGIN_DEVICE,
    ORIGIN_MEASURED,
    ORIGIN_OTHER,
    channel_name,
    measurement_of,
    origin_of,
    origin_of_measurement,
    payload_kind_of_measurement,
    split_channel,
)

# payload_kind, the measurement writer/point_builders.py stores, the origin.
FAMILIES = [
    ("telemetry:environment_metrics", "environment_metrics", ORIGIN_MEASURED),
    ("telemetry:device_metrics", "device_metrics", ORIGIN_MEASURED),
    ("device:nodeinfo", "nodeinfo", ORIGIN_DEVICE),
    ("device:position", "position", ORIGIN_DEVICE),
    ("device:portnum_67", "portnum_67", ORIGIN_DEVICE),
    ("computed:derived", "derived", ORIGIN_COMPUTED),
    ("computed:quality", "quality", ORIGIN_COMPUTED),
    ("computed:alarms", "alarms", ORIGIN_COMPUTED),
]


@pytest.mark.parametrize("payload_kind,measurement,_origin", FAMILIES)
def test_measurement_of_flattens_to_the_stored_name(payload_kind, measurement, _origin):
    assert measurement_of(payload_kind) == measurement


@pytest.mark.parametrize("payload_kind,measurement,_origin", FAMILIES)
def test_reading_a_measurement_back_recovers_its_payload_kind(payload_kind, measurement, _origin):
    assert payload_kind_of_measurement(measurement) == payload_kind


@pytest.mark.parametrize("payload_kind,measurement,_origin", FAMILIES)
def test_channel_splits_back_into_the_pair_it_was_built_from(payload_kind, measurement, _origin):
    channel = channel_name(payload_kind, "some_field")
    assert channel == f"{measurement}.some_field"
    assert split_channel(channel) == (measurement, "some_field")


@pytest.mark.parametrize("payload_kind,measurement,origin", FAMILIES)
def test_origin_names_the_producer(payload_kind, measurement, origin):
    assert origin_of(payload_kind) == origin
    # One definition, not two that can drift apart.
    assert origin_of_measurement(measurement) == origin

def test_an_unrecognised_namespace_is_other():
    assert origin_of("something:else") == ORIGIN_OTHER
    assert origin_of("") == ORIGIN_OTHER
