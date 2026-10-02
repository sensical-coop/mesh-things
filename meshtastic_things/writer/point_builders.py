from datetime import datetime, timezone

import structlog
from influxdb_client import Point

from common.channels import (
    ALARMS,
    DERIVED,
    DERIVED_KIND,
    DEVICE,
    NODEINFO,
    NODEINFO_KIND,
    POSITION,
    POSITION_KIND,
    TELEMETRY,
    measurement_of,
)
from common.timestamps import resolve_timestamp

log = structlog.get_logger()

# payload_kind values that are intentionally not persisted (logged at debug though).
SKIP_PAYLOAD_KINDS = {
    f"{DEVICE}:portnum_1",  # TEXT_MESSAGE_APP - free text, not a timeseries metric
    f"{DEVICE}:portnum_5",  # ROUTING_APP - mesh routing/ack control traffic
}


def _convert_date(timestamp: int) -> str:
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _base_point_dict(event: dict, measurement: str) -> dict:
    timestamp, quality = resolve_timestamp(event)
    tags = {"node_id": event["node_id"]}
    if event.get("mesh_id"):
        # node_id alone is not unique
        tags["mesh_id"] = event["mesh_id"]
    if event.get("channel_id"):
        tags["channel_id"] = event["channel_id"]
    if event.get("gateway_id"):
        tags["gateway_id"] = event["gateway_id"]
    return {
        "measurement": measurement,
        "tags": tags,
        "fields": {
            "packet_id": event["packet_id"],
            "timestamp_quality": quality,
        },
        "time": _convert_date(timestamp),
    }


def build_telemetry_points(event: dict) -> list[Point]:
    """One Point per populated Telemetry sub-metric dict (device_metrics, environment_metrics,
    etc.). Handles the (rare in practice) case of multiple sub-metrics present at once instead
    of silently picking whichever dict-valued key was seen last, like the code this replaces."""
    payload = event.get("payload") or {}
    points = []
    for key, value in payload.items():
        if key == "time" or not isinstance(value, dict):
            continue
        point_dict = _base_point_dict(event, key)
        for field, field_value in value.items():
            try:
                point_dict["fields"][field] = float(field_value)
            except (TypeError, ValueError):
                continue
        points.append(Point.from_dict(point_dict))
    return points


def build_position_points(event: dict) -> list[Point]:
    payload = event.get("payload") or {}
    point_dict = _base_point_dict(event, POSITION)
    if "latitude_i" in payload:
        point_dict["fields"]["latitude"] = payload["latitude_i"] / 1e7
    if "longitude_i" in payload:
        point_dict["fields"]["longitude"] = payload["longitude_i"] / 1e7
    if "altitude" in payload:
        try:
            point_dict["fields"]["altitude"] = float(payload["altitude"])
        except (TypeError, ValueError):
            pass
    if len(point_dict["fields"]) <= 2:  # nothing beyond packet_id/timestamp_quality
        return []
    return [Point.from_dict(point_dict)]


def build_nodeinfo_points(event: dict) -> list[Point]:
    payload = event.get("payload") or {}
    point_dict = _base_point_dict(event, NODEINFO)
    for tag_field in ("long_name", "short_name", "hw_model", "role"):
        if payload.get(tag_field):
            point_dict["tags"][tag_field] = str(payload[tag_field])
    if payload.get("id"):
        point_dict["fields"]["user_id"] = str(payload["id"])
    return [Point.from_dict(point_dict)]


def build_generic_points(event: dict) -> list[Point]:
    """Fallback for any payload_kind without a dedicated builder above, so a
    brand-new portnum gets *something* persisted without requiring a code change first."""
    payload = event.get("payload") or {}
    point_dict = _base_point_dict(event, measurement_of(event.get("payload_kind")))
    for key, value in payload.items():
        if isinstance(value, bool) or isinstance(value, (int, float)):
            point_dict["fields"][key] = value
    if len(point_dict["fields"]) <= 2:  # nothing beyond packet_id/timestamp_quality
        return []
    return [Point.from_dict(point_dict)]


def build_derived_points(event: dict) -> list[Point]:
    """Channels computed by postprocessing, one point per event.

    Tagged with the postprocessing that produced them. There is no packet_id:
    a derived event can combine samples from several packets.
    """
    tags = {"node_id": event["node_id"], "postprocessing_id": event["postprocessing_id"]}
    if event.get("mesh_id"):
        tags["mesh_id"] = event["mesh_id"]
    fields = {
        field: float(value)
        for field, value in ((event.get("payload") or {}).get(DERIVED) or {}).items()
        if isinstance(value, (int, float)) and not isinstance(value, bool)
    }
    if not fields:
        return []
    point_dict = {"measurement": DERIVED, "tags": tags, "fields": fields, "time": _convert_date(event["rx_time"])}
    return [Point.from_dict(point_dict)]


def build_alarm_points(event: dict) -> list[Point]:
    """Quality alarm events have a different shape from decoded messages - no
    packet_id/rx_time/payload_kind - so they don't go through _base_point_dict
    like the builders above. Example:

        {mesh_id, device_id, channel, detector, source, value, message, triggered_at}

    """
    device_id = event.get("device_id", event.get("node_id"))
    channel = event.get("channel", event.get("field"))

    tags = {"detector": event["detector"]}

    if device_id is not None:
        tags["node_id"] = str(device_id)
    if event.get("mesh_id"):
        # node_id alone is not unique
        tags["mesh_id"] = event["mesh_id"]
    if channel:
        # Absent for device alarms.
        tags["channel"] = channel
    if event.get("source"):
        # "stream" or "batch" detection.
        tags["source"] = event["source"]
    if event.get("repeat"):
        # Continues a condition already alarmed; the daily counts tell new ones apart.
        tags["repeat"] = "true"

    fields = {"message": str(event.get("message", ""))}
    value = event.get("value")
    if value is not None:
        fields["value"] = float(value)

    point_dict = {
        "measurement": ALARMS,
        "tags": tags,
        "fields": fields,
        "time": event["triggered_at"],
    }
    return [Point.from_dict(point_dict)]


def get_points(event: dict) -> list[Point]:
    if "detector" in event:  # alarm event, not a decoded telemetry message
        return build_alarm_points(event)

    payload_kind = event.get("payload_kind", "") or ""
    if payload_kind in SKIP_PAYLOAD_KINDS:
        log.debug("Skipping payload kind", payload_kind=payload_kind)
        return []
    if payload_kind.startswith(TELEMETRY):
        return build_telemetry_points(event)
    if payload_kind == DERIVED_KIND:
        return build_derived_points(event)
    if payload_kind == POSITION_KIND:
        return build_position_points(event)
    if payload_kind == NODEINFO_KIND:
        return build_nodeinfo_points(event)
    return build_generic_points(event)
