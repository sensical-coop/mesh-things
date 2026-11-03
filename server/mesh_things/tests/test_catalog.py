import pytest

pytest.importorskip("meshtastic", reason="needs mesh-things[protobuf]")

from meshtastic.protobuf import telemetry_pb2

from mesh_things.catalog import is_catalogued, telemetry_variants


def _field(message, name):
    return message.DESCRIPTOR.fields_by_name[name]


def test_numeric_scalars_are_catalogued():
    assert is_catalogued(_field(telemetry_pb2.EnvironmentMetrics, "temperature"))


def test_strings_and_repeated_numerics_are_not():
    assert not is_catalogued(_field(telemetry_pb2.HostMetrics, "user_string"))
    assert not is_catalogued(_field(telemetry_pb2.EnvironmentMetrics, "one_wire_temperature"))


def test_one_entry_per_telemetry_variant():
    variants = {v.payload_kind: v for v in telemetry_variants()}
    oneof = telemetry_pb2.Telemetry.DESCRIPTOR.oneofs_by_name["variant"]
    assert set(variants) == {f"telemetry:{f.name}" for f in oneof.fields}
    environment = variants["telemetry:environment_metrics"]
    assert environment.message_name == "EnvironmentMetrics"
    assert "temperature" in environment.field_names
    assert "one_wire_temperature" not in environment.field_names
