"""Which sinks each device's readings are sent to, published to mesh.sink_config.v1.

The published lists are the effective ones, so consumers apply them as is. A device's
list holds the archive while an allowed registration of the node opts in, and the MQTT
sinks attached to that node. A mesh's list holds the MQTT sinks attached to the whole
mesh. Nothing is listed unless the mesh's owner is an operator.
"""
from django.db import transaction
from django.utils import timezone

from common import sinks as sink_names

from .data_store import get_data_store
from .kafka_publisher import get_publisher
from .models import Device, DeviceSink, Mesh, MeshSink, Owner, Sink, SinkInstruction

ARCHIVE = "archive"


def archive_available() -> bool:
    """Whether this instance runs the Parquet archive (not on the lite profile)."""
    return bool(get_data_store().archive_bucket)


def device_sinks(mesh: Mesh, device_id: int) -> list[str]:
    if not mesh.owner.is_operator:
        return []
    allowed = Device.objects.filter(mesh=mesh, device_id=device_id, is_allowed=True)
    found = [ARCHIVE] if allowed.filter(archive_enabled=True).exists() else []
    sink_ids = DeviceSink.objects.filter(device__in=allowed).values_list("sink_id", flat=True).distinct()
    return found + sorted(sink_names.ref(sink_id) for sink_id in sink_ids)


def mesh_sinks(mesh: Mesh) -> list[str]:
    if not mesh.owner.is_operator:
        return []
    return sorted(sink_names.ref(sink_id) for sink_id in mesh.sink_links.values_list("sink_id", flat=True))


def publish_device(device: Device) -> None:
    """Send the node's current sinks. Raises on failure."""
    get_publisher().publish_device_sinks(
        device.mesh_id, device.device_id, device_sinks(device.mesh, device.device_id)
    )


def publish_mesh(mesh: Mesh) -> None:
    """Send the sinks every node of the mesh goes to. Raises on failure."""
    get_publisher().publish_mesh_sinks(mesh.id, mesh_sinks(mesh))


def with_sinks(devices) -> list[Device]:
    """The devices whose readings go to the archive or an MQTT sink."""
    devices = list(devices)
    linked = set(DeviceSink.objects.filter(device__in=devices).values_list("device_id", flat=True))
    return [d for d in devices if d.archive_enabled or d.id in linked]


def record_archive_instruction(device: Device, given_by: Owner) -> None:
    """Record who switched the device's archive on or off, once the pipeline has been told."""
    now = timezone.now()
    device.archive_enabled_at = now if device.archive_enabled else None
    device.archive_enabled_by = given_by if device.archive_enabled else None
    with transaction.atomic():
        device.save(update_fields=["archive_enabled_at", "archive_enabled_by"])
        _instruction(ARCHIVE, device.archive_enabled, given_by, now, device=device)


def _instruction(sink: str, enabled: bool, given_by: Owner, at, device: Device | None = None, mesh: Mesh | None = None):
    SinkInstruction.objects.create(
        sink=sink,
        enabled=enabled,
        device=device,
        mesh_id=device.mesh_id if device else mesh.id,
        node_id=device.device_id if device else None,
        given_by=given_by,
        given_by_name=given_by.name,
        given_by_email=given_by.email,
        given_at=at,
    )


def record_sink_instructions(sink: Sink, given_by: Owner, meshes: dict, devices: dict) -> None:
    """Record each mesh or device attached to or detached from an MQTT sink.

    Args:
        meshes: Mesh to True when attached, False when detached.
        devices: Device to True when attached, False when detached.
    """
    now = timezone.now()
    ref = sink_names.ref(sink.id)
    with transaction.atomic():
        for mesh, enabled in meshes.items():
            _instruction(ref, enabled, given_by, now, mesh=mesh)
        for device, enabled in devices.items():
            _instruction(ref, enabled, given_by, now, device=device)


def unpublish_devices(devices) -> None:
    """Send no sinks for devices about to be deleted. Raises on failure."""
    publisher = get_publisher()
    for mesh_id, device_id in {(d.mesh_id, d.device_id) for d in with_sinks(devices)}:
        publisher.publish_device_sinks(mesh_id, device_id, [])


def unpublish_meshes(meshes) -> None:
    """Send no sinks for meshes about to be deleted. Raises on failure."""
    publisher = get_publisher()
    for mesh_id in MeshSink.objects.filter(mesh__in=list(meshes)).values_list("mesh_id", flat=True).distinct():
        publisher.publish_mesh_sinks(mesh_id, [])


def publish_owner(owner: Owner) -> None:
    """Republish every device and mesh of the owner with a sink, after their role changed. Raises on failure."""
    devices = Device.objects.filter(mesh__owner=owner).select_related("mesh__owner")
    for device in with_sinks(devices):
        publish_device(device)
    for mesh in Mesh.objects.filter(owner=owner, sink_links__isnull=False).distinct().select_related("owner"):
        publish_mesh(mesh)
