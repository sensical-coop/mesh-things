from mesh_things.timestamps import PAYLOAD, RECEIVED, RX_TIME, resolve_timestamp

RX_TIME_S = 1700000000


def test_the_payload_time_wins_when_plausible():
    event = {"rx_time": RX_TIME_S, "received_at": 1700000005000, "payload": {"time": 1699999000}}

    assert resolve_timestamp(event) == (1699999000, PAYLOAD)


def test_an_implausible_payload_time_falls_back_to_the_gateway():
    event = {"rx_time": RX_TIME_S, "received_at": 1700000005000, "payload": {"time": 12}}

    assert resolve_timestamp(event) == (RX_TIME_S, RX_TIME)


def test_a_gateway_without_a_clock_falls_back_to_the_pipeline():
    event = {"rx_time": 0, "received_at": 1700000005999, "payload": {}}

    assert resolve_timestamp(event) == (1700000005, RECEIVED)


def test_an_event_without_a_reception_time_keeps_the_gateway_time():
    assert resolve_timestamp({"rx_time": RX_TIME_S}) == (RX_TIME_S, RX_TIME)
