import pytest

pytest.importorskip("google.protobuf", reason="needs mesh-things[protobuf]")

from mesh_things import protocols
from mesh_things.catalog import is_catalogued, telemetry_variants
from mesh_things.protocols.v2_7 import telemetry_pb2


def _field(message, name):
    return message.DESCRIPTOR.fields_by_name[name]


def test_numeric_scalars_are_catalogued():
    assert is_catalogued(_field(telemetry_pb2.EnvironmentMetrics, "temperature"))


def test_strings_and_repeated_numerics_are_not():
    assert not is_catalogued(_field(telemetry_pb2.HostMetrics, "user_string"))
    assert not is_catalogued(_field(telemetry_pb2.EnvironmentMetrics, "one_wire_temperature"))


def test_one_entry_per_telemetry_variant_of_any_protocol():
    variants = {v.payload_kind: v for v in telemetry_variants()}
    every = {
        f"telemetry:{f.name}"
        for version in protocols.VERSIONS
        for f in protocols.get(version).telemetry_pb2.Telemetry.DESCRIPTOR.oneofs_by_name["variant"].fields
    }
    assert set(variants) == every
    environment = variants["telemetry:environment_metrics"]
    assert environment.message_name == "EnvironmentMetrics"
    assert "temperature" in environment.field_names
    assert "one_wire_temperature" not in environment.field_names


def test_a_variant_a_later_protocol_introduces_is_catalogued():
    variants = {v.payload_kind: v for v in telemetry_variants()}

    assert "solar_irradiance" in variants["telemetry:soil_water_metrics"].field_names


def test_a_later_protocol_adds_fields_after_the_ones_already_known():
    environment = next(v for v in telemetry_variants() if v.payload_kind == "telemetry:environment_metrics")
    known = tuple(f.name for f in telemetry_pb2.EnvironmentMetrics.DESCRIPTOR.fields if is_catalogued(f))

    assert environment.field_names[: len(known)] == known
    assert "lightning_distance_km" in environment.field_names[len(known):]
