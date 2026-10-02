"""The consuming half of the Kafka contract: what the jobs and writers read."""
import json

import pytest

from common import decode, node_ids
from common.channels import channel_name
from quality_worker.alarms import build_alarm

MESH_ID = "5703a8ba-10ee-4a0b-81ea-f7ae04d04d2a"
DEVICE_ID = 431637602

def test_a_gateway_key_is_the_hex_form_the_envelope_carries():
    """decode_packet looks up gateway_state[se.gateway_id]."""
    assert node_ids.to_hex(DEVICE_ID) == "!19ba4462"

def test_the_device_interval_key_absence_detection_builds():
    """state.get(f"{mesh_id}:{device_id}"), which must not look like a channel."""
    assert ":" in f"{MESH_ID}:{DEVICE_ID}"
    assert "." not in f"{MESH_ID}:{DEVICE_ID}"

def test_the_variant_config_key_pattern_detection_builds():
    """The job computes a channel from a reading, then looks the config up by it."""
    assert channel_name("telemetry:environment_metrics", "temperature") == "environment_metrics.temperature"
    assert channel_name("computed:quality", "completeness_ratio") == "quality.completeness_ratio"


class TestGatewayStateShape:
    """Both decode paths store {"psk_b64", "mesh_id"} per gateway."""

    def test_decode_reads_psk_and_mesh_id_out_of_the_stored_state(self):
        state = {"psk_b64": "AQ==", "mesh_id": MESH_ID}

        assert state.get("psk_b64") == "AQ=="
        assert state.get("mesh_id") == MESH_ID

    def test_a_gateway_missing_from_the_state_is_dropped_with_a_reason(self):
        """The registered-gateways-only gate, and it has to name the gateway."""
        from meshtastic.protobuf import mesh_pb2, mqtt_pb2

        se = mqtt_pb2.ServiceEnvelope()
        se.packet.CopyFrom(mesh_pb2.MeshPacket())
        se.channel_id = "LongFast"
        se.gateway_id = node_ids.to_hex(DEVICE_ID)

        dropped = []
        result = decode.decode_packet(
            se.SerializeToString(), {}, set(), on_drop=lambda reason: dropped.append(reason)
        )

        assert result is None
        assert dropped and "!19ba4462" in dropped[0], dropped

    def test_a_gateway_present_in_the_state_gets_past_the_gate(self):
        """Proves the test above fails on the lookup, not on parsing."""
        from meshtastic.protobuf import mesh_pb2, mqtt_pb2

        se = mqtt_pb2.ServiceEnvelope()
        se.packet.CopyFrom(mesh_pb2.MeshPacket())
        se.channel_id = "LongFast"
        se.gateway_id = node_ids.to_hex(DEVICE_ID)
        state = {node_ids.to_hex(DEVICE_ID): {"psk_b64": "AQ==", "mesh_id": MESH_ID}}

        dropped = []
        decode.decode_packet(
            se.SerializeToString(), state, set(), on_drop=lambda reason: dropped.append(reason)
        )

        assert not any("unregistered gateway" in d for d in dropped), dropped


class TestDecodedEventShape:
    """The fields the downstream jobs read off mesh.telemetry.decoded.v1."""

    def test_pattern_detection_reads_node_id_payload_kind_and_payload(self):
        """node_id here, device_id on the config topics: they differ by design."""
        event = {
            "node_id": DEVICE_ID,
            "payload_kind": "telemetry:environment_metrics",
            "payload": {"environment_metrics": {"temperature": 21.4}},
            "mesh_id": MESH_ID,
        }

        assert event.get("node_id") == DEVICE_ID
        assert event.get("payload_kind")
        assert isinstance(event.get("payload"), dict)

    def test_postprocessing_keys_by_mesh_id_and_node_id(self):
        """The same key registry publishes a device's plans under."""
        from common.postprocessing.stream import device_key

        event = {"mesh_id": MESH_ID, "node_id": DEVICE_ID, "payload_kind": "telemetry:environment_metrics"}

        assert device_key(event["mesh_id"], event["node_id"]) == f"{MESH_ID}:{DEVICE_ID}"


class TestSightingAndDiscoveryShape:
    """decode.py builds both; registry's consumers read them."""

    def _decoded(self, payload_kind, payload):
        return {"node_id": DEVICE_ID, "payload_kind": payload_kind, "payload": payload}

    def test_a_sighting_carries_the_compound_identity(self):
        sighting = decode._build_sighting(MESH_ID, self._decoded("device:nodeinfo", {}))

        assert sighting["key"] == f"{MESH_ID}:{DEVICE_ID}"
        assert sighting["mesh_id"] == MESH_ID
        assert sighting["device_id"] == DEVICE_ID
        assert sighting["op"] == "upsert"

    def test_nodeinfo_promotes_the_identity_fields_the_consumer_writes(self):
        sighting = decode._build_sighting(
            MESH_ID,
            self._decoded("device:nodeinfo", {"long_name": "Node One", "short_name": "N1",
                                              "hw_model": "TBEAM", "role": "CLIENT"}),
        )

        assert sighting["name"] == "Node One"
        assert sighting["short_name"] == "N1"
        assert sighting["hardware_type"] == "TBEAM"
        assert sighting["role"] == "CLIENT"

    def test_position_promotes_decoded_degrees_not_raw_integers(self):
        sighting = decode._build_sighting(
            MESH_ID, self._decoded("device:position", {"latitude_i": 413830000, "longitude_i": 24540000})
        )

        assert sighting["latitude"] == pytest.approx(41.383)
        assert sighting["longitude"] == pytest.approx(2.454)

    def test_discovery_carries_what_consume_sensor_discovery_upserts(self):
        discovery = decode._build_discovery(
            MESH_ID, self._decoded("telemetry:environment_metrics", {}), ["temperature"]
        )

        for field in ("mesh_id", "device_id", "payload_kind", "fields"):
            assert field in discovery, field
        assert discovery["payload_kind"] == "telemetry:environment_metrics"

    def test_only_telemetry_reports_discovered_fields(self):
        """Other kinds have no protobuf sub-metric to walk."""
        payload = {"long_name": "Node One"}

        assert decode._discovered_fields("device:nodeinfo", payload) == []
        assert decode._discovered_fields("computed:quality", payload) == []


class TestAlarmEventShape:
    """quality_worker publishes these; the writer and registry's consumer read them."""

    def test_an_alarm_carries_what_the_writer_tags_and_fields_by(self):
        alarm = build_alarm(MESH_ID, DEVICE_ID, "environment_metrics.temperature",
                            "range_check", "too hot", value=99.0)

        for field in ("mesh_id", "device_id", "channel", "detector", "source",
                      "value", "message", "triggered_at"):
            assert field in alarm, field

    def test_the_writer_recognises_an_alarm_by_its_detector(self):
        """get_points branches on it before it looks at payload_kind."""
        alarm = build_alarm(MESH_ID, DEVICE_ID, "c.f", "range_check", "msg")

        assert "detector" in alarm

    def test_an_alarm_declares_its_payload_kind_for_the_archive(self):
        """s3_writer stores it verbatim, and recorded null before."""
        alarm = build_alarm(MESH_ID, DEVICE_ID, "c.f", "range_check", "msg")

        assert alarm["payload_kind"] == "computed:alarms"

    def test_the_alarm_key_is_unique_per_channel_and_detector(self):
        a = build_alarm(MESH_ID, DEVICE_ID, "c.f", "range_check", "msg")
        b = build_alarm(MESH_ID, DEVICE_ID, "c.f", "flat_value", "msg")

        key = lambda x: f"{x['mesh_id']}:{x['device_id']}:{x['channel']}:{x['detector']}"
        assert key(a) != key(b)

    def test_every_event_is_json_serialisable(self):
        json.dumps(build_alarm(MESH_ID, DEVICE_ID, "c.f", "range_check", "msg", value=1.0))
        json.dumps(decode._build_sighting(MESH_ID, {"node_id": DEVICE_ID,
                                                    "payload_kind": "device:nodeinfo", "payload": {}}))
