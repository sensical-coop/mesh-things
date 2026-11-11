"""The time a decoded reading was taken, shared so that every consumer agrees on it."""

MIN_FEASIBLE_TIME = 1577836800  # 2020-01-01 in epoch (s)

PAYLOAD = "payload"
RX_TIME = "rx_time"
RECEIVED = "received"


def resolve_timestamp(event: dict) -> tuple[int, str]:
    """Epoch seconds of a decoded event and where they came from.

    The payload's own time wins when it is plausible, because a device
    delivering stored history reports when each reading was taken, not when it
    was received. Then the time the gateway heard the packet, and last the time
    the pipeline received it, for a gateway without a clock.
    """
    payload_time = (event.get("payload") or {}).get("time")
    if payload_time and payload_time > MIN_FEASIBLE_TIME:
        return payload_time, PAYLOAD
    rx_time = event.get("rx_time") or 0
    received_at = event.get("received_at")
    if rx_time <= MIN_FEASIBLE_TIME and received_at:
        return received_at // 1000, RECEIVED
    return rx_time, RX_TIME
