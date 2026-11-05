"""Readings and archived payloads as Meshtastic protobuf messages. Needs mesh-things[protobuf].

Values are in the units the API stores, which are those of the canonical protocol,
`mesh_things.protocols.CANONICAL`. Each function builds the messages of one protocol
version, `protocol`, which defaults to the canonical one.
"""
from collections import defaultdict
from datetime import datetime

try:
    from google.protobuf import json_format
    from google.protobuf.message import Message
    from mesh_things import protocols
except ImportError as error:
    raise ImportError("mesh_things.protobuf needs the protobufs: pip install 'mesh-things[protobuf]'") from error

from mesh_things.channels import TELEMETRY, measurement_of, namespace_of, split_channel
from mesh_things.portnum_registry import message_type


def payload_message(payload_kind: str, payload: dict, protocol: str = protocols.CANONICAL) -> Message:
    """An archived payload (an archive row's `payload_json`, decoded) as its protobuf message."""
    factory = message_type(payload_kind, protocol)
    if factory is None:
        raise ValueError(f"{payload_kind} has no protobuf message")
    return _parse(payload, factory())


def latest_messages(latest: dict, protocol: str = protocols.CANONICAL) -> dict[str, Message]:
    """A device's latest readings, every channel at once, as one `Telemetry` per variant.

    Readings that are not telemetry (positions, derived and quality channels) are left out,
    since the API stores them in a form of its own rather than as the protobuf's fields.
    So are variants the protocol version does not have, such as `soil_water_metrics`
    before 2.8.
    """
    variants = _variants(protocol)
    fields: dict[str, dict] = defaultdict(dict)
    times: dict[str, list[str]] = defaultdict(list)
    for reading in latest["readings"]:
        if namespace_of(reading["payload_kind"]) == TELEMETRY and measurement_of(reading["payload_kind"]) in variants:
            fields[reading["payload_kind"]][reading["field_name"]] = reading["value"]
            times[reading["payload_kind"]].append(reading["time"])
    return {kind: _telemetry(kind, values, max(times[kind]), protocol) for kind, values in fields.items()}


def series_messages(readings: dict, protocol: str = protocols.CANONICAL) -> list[tuple[str, Message]]:
    """Raw readings of one telemetry variant as `(time, Telemetry)` pairs, oldest first.

    Readings averaged over a `window` cannot be converted: a mean of integer fields is
    usually not an integer.
    """
    payload_kind = readings["payload_kind"]
    if namespace_of(payload_kind) != TELEMETRY:
        raise ValueError(f"{payload_kind} is not telemetry, so it has no protobuf message")
    by_time: dict[str, dict] = defaultdict(dict)
    for series in readings["series"]:
        _, field = split_channel(series["channel"])
        for point in series["points"]:
            if point["value"] is not None:
                by_time[point["time"]][field] = point["value"]
    return [(time, _telemetry(payload_kind, by_time[time], time, protocol)) for time in sorted(by_time)]


def _variants(protocol: str) -> set[str]:
    telemetry = protocols.get(protocol).telemetry_pb2.Telemetry
    return {field.name for field in telemetry.DESCRIPTOR.oneofs_by_name["variant"].fields}


def _telemetry(payload_kind: str, values: dict, time: str, protocol: str) -> Message:
    message = _parse({measurement_of(payload_kind): values}, protocols.get(protocol).telemetry_pb2.Telemetry())
    message.time = int(datetime.fromisoformat(time.replace("Z", "+00:00")).timestamp())
    return message


def _parse(values: dict, message: Message) -> Message:
    try:
        return json_format.ParseDict(values, message)
    except json_format.ParseError as error:
        raise ValueError(f"Does not fit {message.DESCRIPTOR.full_name}: {error}") from error
