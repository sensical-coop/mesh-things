"""Registering gateways, by their owner or by gateway discovery."""
import base64

import structlog
from django.db import transaction
from django.utils import timezone

from mesh_things import codec, node_ids

from .exceptions import BadGateway
from .kafka_publisher import get_publisher, publish_gateway_state
from .models import Device, Mesh

log = structlog.get_logger()


def save_gateway(device: Device, update_fields: list[str] | None = None) -> None:
    """Save a gateway and register it with the decoder, as one change.

    Raises:
        IntegrityError: Another allowed gateway already has this node number.
        BadGateway: The registration could not be published; the save is rolled back.
    """
    with transaction.atomic():
        device.save(update_fields=update_fields)
        try:
            publish_gateway_state(get_publisher(), device, device.mesh)
        except Exception as e:
            raise BadGateway(f"Failed to publish gateway registration, rolled back: {e}")


def _matching_mesh(source_id: str | None, channel_id: str, raw: bytes) -> Mesh | None:
    """The one mesh on this source and channel whose PSK decodes the sample, if it has discovery on.

    Every mesh is tried, not only those with discovery on: when two share a channel
    and PSK, taking the gateway for one would lock the other owner out of it.
    """
    matches = [
        mesh
        for mesh in Mesh.objects.filter(source_id=source_id, channel_id=channel_id)
        if codec.decodes_with(raw, mesh.psk_b64)
    ]
    if len(matches) > 1:
        log.info("Gateway discovery skipped an ambiguous match", meshes=[str(m.id) for m in matches])
        return None
    if not matches or not matches[0].discover_gateways:
        return None
    return matches[0]


def discover_gateway(event: dict) -> Device | None:
    """Register the gateway a traffic sample came from, if it proves to belong to exactly one mesh.

    Nothing happens when the gateway already has an allowed registration anywhere,
    or a rejected one on the matching mesh, so rejecting it keeps it out. A node
    already registered on that mesh becomes its gateway.
    """
    source_id, channel_id = event.get("source_id"), event["channel_id"]
    gateway_num = node_ids.to_num(event["gateway_id"])
    if gateway_num is None:
        return None
    # Skip before decrypting anything, which is what most samples come down to.
    if not Mesh.objects.filter(source_id=source_id, channel_id=channel_id, discover_gateways=True).exists():
        return None
    raw = base64.b64decode(event["sample_b64"])
    # The decoder looks the gateway up by both, so they must agree.
    if codec.parse_envelope(raw).gateway_id != event["gateway_id"]:
        return None
    mesh = _matching_mesh(source_id, channel_id, raw)
    if mesh is None:
        return None
    if Device.objects.filter(device_id=gateway_num, is_gateway=True, is_allowed=True).exists():
        return None

    rows = Device.objects.filter(mesh=mesh, device_id=gateway_num)
    if rows.filter(is_allowed=False).exists():
        return None
    device = rows.first()
    if device is None:
        device = Device(mesh=mesh, device_id=gateway_num, is_gateway=True, discovered_at=timezone.now())
        save_gateway(device)
    else:
        device.is_gateway = True
        device.discovered_at = timezone.now()
        save_gateway(device, update_fields=["is_gateway", "discovered_at", "updated_at"])
    log.info("Gateway discovered", mesh_id=str(mesh.id), gateway_id=event["gateway_id"])
    return device
