"""Readings and archived payloads as Meshtastic protobuf messages. Needs mesh-things[protobuf].

Values are in the units the API stores, which are those of the `meshtastic` release this
package pins.
"""
from collections import defaultdict
from datetime import datetime

try:
    from google.protobuf import json_format
    from google.protobuf.message import Message
    from meshtastic.protobuf import telemetry_pb2
except ImportError as error:
    raise ImportError("mesh_things.protobuf needs the protobufs: pip install 'mesh-things[protobuf]'") from error

from mesh_things.channels import TELEMETRY, measurement_of, namespace_of, split_channel
from mesh_things.portnum_registry import message_type


def payload_message(payload_kind: str, payload: dict) -> Message:
    """An archived payload (an archive row's `payload_json`, decoded) as its protobuf message."""
    factory = message_type(payload_kind)
    if factory is None:
        raise ValueError(f"{payload_kind} has no protobuf message")
    return _parse(payload, factory())


def latest_messages(latest: dict) -> dict[str, telemetry_pb2.Telemetry]:
    """A device's latest readings, every channel at once, as one `Telemetry` per variant.

    Readings that are not telemetry (positions, derived and quality channels) are left out,
    since the API stores them in a form of its own rather than as the protobuf's fields.
    """
    fields: dict[str, dict] = defaultdict(dict)
    times: dict[str, list[str]] = defaultdict(list)
    for reading in latest["readings"]:
        if namespace_of(reading["payload_kind"]) == TELEMETRY:
            fields[reading["payload_kind"]][reading["field_name"]] = reading["value"]
            times[reading["payload_kind"]].append(reading["time"])
    return {kind: _telemetry(kind, values, max(times[kind])) for kind, values in fields.items()}


def series_messages(readings: dict) -> list[tuple[str, telemetry_pb2.Telemetry]]:
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
    return [(time, _telemetry(payload_kind, by_time[time], time)) for time in sorted(by_time)]


def _telemetry(payload_kind: str, values: dict, time: str) -> telemetry_pb2.Telemetry:
    message = _parse({measurement_of(payload_kind): values}, telemetry_pb2.Telemetry())
    message.time = int(datetime.fromisoformat(time.replace("Z", "+00:00")).timestamp())
    return message


def _parse(values: dict, message: Message) -> Message:
    try:
        return json_format.ParseDict(values, message)
    except json_format.ParseError as error:
        raise ValueError(f"Does not fit {message.DESCRIPTOR.full_name}: {error}") from error
