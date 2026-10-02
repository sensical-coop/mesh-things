"""Which sinks each device's readings are sent to, published to mesh.sink_config.v1.

The published list is the effective one, so consumers apply it as is: the archive
is listed while an allowed registration of the node opts in and the mesh's owner is
an operator.
"""
from django.db import transaction
from django.utils import timezone

from .data_store import get_data_store
from .kafka_publisher import get_publisher
from .models import Device, Mesh, Owner, SinkInstruction

ARCHIVE = "archive"


def archive_available() -> bool:
    """Whether this instance runs the Parquet archive (not on the lite profile)."""
    return bool(get_data_store().archive_bucket)


def device_sinks(mesh: Mesh, device_id: int) -> list[str]:
    archived = (
        mesh.owner.is_operator
        and Device.objects.filter(mesh=mesh, device_id=device_id, is_allowed=True, archive_enabled=True).exists()
    )
    return [ARCHIVE] if archived else []


def publish_device(device: Device) -> None:
    """Send the node's current sinks. Raises on failure."""
    get_publisher().publish_device_sinks(
        device.mesh_id, device.device_id, device_sinks(device.mesh, device.device_id)
    )


def record_archive_instruction(device: Device, given_by: Owner) -> None:
    """Record who switched the device's archive on or off, once the pipeline has been told."""
    now = timezone.now()
    device.archive_enabled_at = now if device.archive_enabled else None
    device.archive_enabled_by = given_by if device.archive_enabled else None
    with transaction.atomic():
        device.save(update_fields=["archive_enabled_at", "archive_enabled_by"])
        SinkInstruction.objects.create(
            sink=ARCHIVE,
            enabled=device.archive_enabled,
            device=device,
            mesh_id=device.mesh_id,
            node_id=device.device_id,
            given_by=given_by,
            given_by_name=given_by.name,
            given_by_email=given_by.email,
            given_at=now,
        )


def unpublish_devices(devices) -> None:
    """Send no sinks for devices about to be deleted. Raises on failure."""
    publisher = get_publisher()
    for mesh_id, device_id in {(d.mesh_id, d.device_id) for d in devices if d.archive_enabled}:
        publisher.publish_device_sinks(mesh_id, device_id, [])


def publish_owner(owner: Owner) -> None:
    """Republish every archived device on the owner's meshes after their role changed. Raises on failure."""
    for device in Device.objects.filter(mesh__owner=owner, archive_enabled=True).select_related("mesh__owner"):
        publish_device(device)
