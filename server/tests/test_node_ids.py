"""Node ids tests"""
from meshtastic.protobuf import mesh_pb2, mqtt_pb2, telemetry_pb2

from mesh_things import codec, node_ids
from writer.point_builders import get_points


class TestParsing:
    def test_it_reads_the_wire_form(self):
        assert node_ids.to_num("!19ba4462") == 431637602

    def test_an_already_converted_value_passes_through(self):
        assert node_ids.to_num(431637602) == 431637602

    def test_a_bare_decimal_string_is_refused_rather_than_guessed(self):
        assert node_ids.to_num("431637602") is None

    def test_rubbish_gives_nothing(self):
        for value in ("!nothex", "", "!", None, "19ba4462"):
            assert node_ids.to_num(value) is None, value

    def test_the_two_forms_round_trip(self):
        for num in (0, 1, 431637602, 0xAABBCCDD, 0xFFFFFFFF):
            assert node_ids.to_num(node_ids.to_hex(num)) == num

    def test_the_wire_form_is_padded_to_eight_digits(self):
        assert node_ids.to_hex(555555) == "!00087a23"


class TestTheIdentityIsShared:
    def _envelope(self, node_num: int, gateway: str) -> bytes:
        telemetry = telemetry_pb2.Telemetry()
        telemetry.device_metrics.battery_level = 87
        packet = mesh_pb2.MeshPacket()
        packet.id = 1
        setattr(packet, "from", node_num)
        packet.rx_time = 1700000000
        packet.decoded.portnum = 67
        packet.decoded.payload = telemetry.SerializeToString()
        envelope = mqtt_pb2.ServiceEnvelope()
        envelope.packet.CopyFrom(packet)
        envelope.channel_id = "LongFast"
        envelope.gateway_id = gateway
        return envelope.SerializeToString()

    def test_a_gateway_reporting_its_own_telemetry_gets_one_identity(self):
        raw = self._envelope(431637602, "!19ba4462")

        event = codec.decode_message(raw, key_bytes=None)

        assert event["gateway_id"] == event["node_id"] == 431637602

    def test_the_influx_tags_are_written_in_the_same_format(self):
        raw = self._envelope(431637602, "!19ba4462")

        line = get_points(codec.decode_message(raw, key_bytes=None))[0].to_line_protocol()

        assert "gateway_id=431637602" in line
        assert "node_id=431637602" in line

    def test_an_unreadable_gateway_id_drops_the_tag_instead_of_mixing_formats(self):
        raw = self._envelope(431637602, "garbled")

        event = codec.decode_message(raw, key_bytes=None)
        line = get_points(event)[0].to_line_protocol()

        assert event["gateway_id"] is None
        assert "gateway_id" not in line
