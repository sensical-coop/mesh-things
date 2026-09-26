"""When a decoded reading was taken, as every consumer of it must agree."""

MIN_FEASIBLE_TIME = 1577836800  # 2020-01-01 in epoch (s)


def resolve_timestamp(event: dict) -> tuple[int, str]:
    """Epoch seconds of a decoded event and where they came from.

    The payload's own time wins when it is plausible, because a device
    delivering stored history reports when each reading was taken, not when it
    was received.
    """
    timestamp = event["rx_time"]
    quality = "rx_time"
    payload_time = (event.get("payload") or {}).get("time")
    if payload_time and payload_time > MIN_FEASIBLE_TIME:
        timestamp = payload_time
        quality = "payload"
    return timestamp, quality
