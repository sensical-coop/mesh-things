import base64
import json
import os
import uuid

from meshtastic.protobuf import mesh_pb2, mqtt_pb2

from mesh_things import codec
from registry.gateways import discover_gateway
from registry.management.commands.consume_gateway_candidates import Command as DiscoveryCommand
from registry.models import Device, Mesh, Owner, OwnerRole

from .helpers import MESH_TERMS, RegistryTestCase

PSK = base64.b64encode(os.urandom(16)).decode()
GATEWAY = "!0000beef"
GATEWAY_NUM = 0xBEEF


def _envelope(psk_b64: str | None, gateway_id: str = GATEWAY, channel_id: str = "Private") -> bytes:
    """A position packet relayed by `gateway_id`, encrypted with `psk_b64`, or plain without one."""
    position = mesh_pb2.Position(latitude_i=1, longitude_i=2)
    data = mesh_pb2.Data(portnum=3, payload=position.SerializeToString())
    mp = mesh_pb2.MeshPacket(id=7)
    setattr(mp, "from", 0x1234)
    key = codec.decode_psk(psk_b64) if psk_b64 else None
    if key:
        mp.encrypted = codec.encrypt_packet(data.SerializeToString(), mp.id, 0x1234, key)
    else:
        mp.decoded.CopyFrom(data)
    se = mqtt_pb2.ServiceEnvelope(channel_id=channel_id, gateway_id=gateway_id)
    se.packet.CopyFrom(mp)
    return se.SerializeToString()


def _event(raw: bytes, source_id=None, channel_id="Private", gateway_id=GATEWAY) -> dict:
    return {
        "source_id": source_id,
        "channel_id": channel_id,
        "gateway_id": gateway_id,
        "seen_at": "2026-10-03T00:00:00+00:00",
        "sample_b64": base64.b64encode(raw).decode(),
    }


class DiscoveryTestCase(RegistryTestCase):
    def setUp(self):
        super().setUp()
        self.owner = self.create_owner()
        self.mesh = self.create_mesh(self.owner, channel_id="Private", psk_b64=PSK)
        self.set_discovery(self.mesh, True)

    @staticmethod
    def set_discovery(mesh: dict, on: bool) -> None:
        Mesh.objects.filter(pk=uuid.UUID(mesh["id"])).update(discover_gateways=on)


class DiscoverGatewayTests(DiscoveryTestCase):
    def test_a_gateway_decoding_with_the_mesh_psk_is_registered(self):
        device = discover_gateway(_event(_envelope(PSK)))

        self.assertIsNotNone(device)
        self.assertEqual(device.device_id, GATEWAY_NUM)
        self.assertEqual(str(device.mesh_id), self.mesh["id"])
        self.assertTrue(device.is_gateway and device.is_allowed)
        self.assertIsNotNone(device.discovered_at)
        self.fake_publisher.publish_gateway_upsert.assert_called_once()

    def test_nothing_is_registered_with_discovery_off(self):
        self.set_discovery(self.mesh, False)

        self.assertIsNone(discover_gateway(_event(_envelope(PSK))))
        self.assertFalse(Device.objects.exists())

    def test_a_packet_encrypted_with_another_key_is_ignored(self):
        other = base64.b64encode(os.urandom(16)).decode()

        self.assertIsNone(discover_gateway(_event(_envelope(other))))
        self.assertFalse(Device.objects.exists())

    def test_a_plain_packet_does_not_prove_an_encrypted_mesh(self):
        self.assertIsNone(discover_gateway(_event(_envelope(None))))

    def test_another_channel_or_source_is_not_matched(self):
        self.assertIsNone(discover_gateway(_event(_envelope(PSK), channel_id="Other")))
        self.assertIsNone(discover_gateway(_event(_envelope(PSK), source_id=str(uuid.uuid4()))))

    def test_an_envelope_naming_another_gateway_is_ignored(self):
        self.assertIsNone(discover_gateway(_event(_envelope(PSK, gateway_id="!0000cafe"))))

    def test_a_mesh_sharing_channel_and_psk_makes_it_ambiguous_even_with_discovery_off(self):
        other_owner = self.create_owner(name="Other", email="other@example.com")
        self.create_mesh(other_owner, channel_id="Private", psk_b64=PSK)

        self.assertIsNone(discover_gateway(_event(_envelope(PSK))))
        self.assertFalse(Device.objects.exists())

    def test_a_gateway_registered_on_another_mesh_is_left_alone(self):
        other_owner = self.create_owner(name="Other", email="other@example.com")
        other_mesh = self.create_mesh(other_owner, channel_id="Elsewhere")
        self.create_gateway(other_owner, other_mesh, device_id=GATEWAY_NUM)

        self.assertIsNone(discover_gateway(_event(_envelope(PSK))))
        self.assertEqual(Device.objects.count(), 1)

    def test_a_rejected_gateway_stays_out(self):
        gateway = self.create_gateway(self.owner, self.mesh, device_id=GATEWAY_NUM)
        self.client.put(
            f"/devices/{gateway['uuid']}", {"is_allowed": False}, format="json", **self.auth_headers(self.owner)
        )

        self.assertIsNone(discover_gateway(_event(_envelope(PSK))))
        self.assertFalse(Device.objects.filter(is_allowed=True).exists())

    def test_a_registered_node_becomes_the_gateway(self):
        node = self.create_node(self.owner, self.mesh, device_id=GATEWAY_NUM)

        device = discover_gateway(_event(_envelope(PSK)))

        self.assertEqual(str(device.id), node["uuid"])
        self.assertTrue(Device.objects.get(pk=device.id).is_gateway)

    def test_a_failed_publish_leaves_nothing_behind(self):
        self.fake_publisher.publish_gateway_upsert.side_effect = RuntimeError("kafka down")

        DiscoveryCommand._handle_record(json.dumps(_event(_envelope(PSK))).encode())

        self.assertFalse(Device.objects.exists())

    def test_a_paused_mesh_gets_the_gateway_but_keeps_it_deregistered(self):
        Mesh.objects.filter(pk=uuid.UUID(self.mesh["id"])).update(paused_at="2026-10-01T00:00:00Z")

        self.assertIsNotNone(discover_gateway(_event(_envelope(PSK))))
        self.fake_publisher.publish_gateway_delete.assert_called_once()
        self.fake_publisher.publish_gateway_upsert.assert_not_called()

    def test_the_mesh_api_shows_where_a_gateway_came_from(self):
        discover_gateway(_event(_envelope(PSK)))

        devices = self.client.get("/devices", **self.auth_headers(self.owner)).json()

        self.assertIsNotNone(devices[0]["discovered_at"])


class DiscoveryToggleTests(RegistryTestCase):
    def setUp(self):
        super().setUp()
        self.owner = self.create_owner()

    def _put(self, mesh, **body):
        return self.client.put(f"/meshes/{mesh['id']}", body, format="json", **self.auth_headers(self.owner))

    def test_an_owner_switches_discovery_on_and_off_for_a_private_psk(self):
        mesh = self.create_mesh(self.owner, psk_b64=PSK)
        self.assertFalse(mesh["discover_gateways"])

        self.assertTrue(self._put(mesh, discover_gateways=True).json()["discover_gateways"])
        self.assertFalse(self._put(mesh, discover_gateways=False).json()["discover_gateways"])

    def test_a_member_cannot_switch_it_on_for_a_well_known_psk(self):
        for psk in ("AQ==", "Ag==", ""):
            mesh = self.create_mesh(self.owner, channel_id=f"C{psk}", psk_b64=psk)
            self.assertEqual(self._put(mesh, discover_gateways=True).status_code, 403, psk)

    def test_a_member_cannot_create_a_mesh_with_it_on_for_the_default_psk(self):
        resp = self.client.post(
            "/meshes",
            {**MESH_TERMS, "channel_id": "LongFast", "psk_b64": "AQ==", "discover_gateways": True},
            format="json",
            **self.auth_headers(self.owner),
        )
        self.assertEqual(resp.status_code, 403)

    def test_a_member_cannot_move_a_discovering_mesh_to_the_default_psk(self):
        mesh = self.create_mesh(self.owner, psk_b64=PSK)
        self._put(mesh, discover_gateways=True)

        self.assertEqual(self._put(mesh, psk_b64="AQ==").status_code, 403)

    def test_other_edits_still_work_after_losing_the_operator_role(self):
        self.promote_to_operator(self.owner)
        mesh = self.create_mesh(self.owner, psk_b64="AQ==")
        self.assertEqual(self._put(mesh, discover_gateways=True).status_code, 200)
        Owner.objects.filter(pk=uuid.UUID(self.owner["id"])).update(role=OwnerRole.MEMBER)

        self.assertEqual(self._put(mesh, label="renamed").status_code, 200)
        self.assertEqual(self._put(mesh, discover_gateways=False).status_code, 200)

    def test_an_operator_may_switch_it_on_for_the_default_psk(self):
        self.promote_to_operator(self.owner)
        mesh = self.create_mesh(self.owner, channel_id="LongFast", psk_b64="AQ==")

        self.assertEqual(self._put(mesh, discover_gateways=True).status_code, 200)
