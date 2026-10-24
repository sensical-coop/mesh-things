import pytest

from mesh_things.protobuf import latest_messages, payload_message, series_messages


def test_latest_readings_become_telemetry_per_variant():
    latest = {"readings": [
        {"payload_kind": "telemetry:device_metrics", "field_name": "battery_level", "value": 90.0,
         "time": "2026-10-24T10:00:00Z"},
        {"payload_kind": "telemetry:device_metrics", "field_name": "voltage", "value": 4.1,
         "time": "2026-10-24T10:05:00Z"},
        {"payload_kind": "device:position", "field_name": "latitude", "value": 41.4, "time": "2026-10-24T10:00:00Z"},
    ]}
    messages = latest_messages(latest)
    assert list(messages) == ["telemetry:device_metrics"]
    message = messages["telemetry:device_metrics"]
    assert message.device_metrics.battery_level == 90
    assert message.time == 1792836300  # 2026-10-24T10:05:00Z, the newest reading


def test_raw_series_become_one_message_per_time():
    readings = {"payload_kind": "telemetry:environment_metrics", "series": [
        {"channel": "environment_metrics.temperature", "points": [{"time": "2026-10-24T10:00:00Z", "value": 21.5}]},
    ]}
    [(time, message)] = series_messages(readings)
    assert time == "2026-10-24T10:00:00Z"
    assert message.environment_metrics.temperature == pytest.approx(21.5)


def test_averaged_integers_do_not_fit():
    readings = {"payload_kind": "telemetry:device_metrics", "series": [
        {"channel": "device_metrics.battery_level", "points": [{"time": "2026-10-24T10:00:00Z", "value": 89.5}]},
    ]}
    with pytest.raises(ValueError, match="battery_level"):
        series_messages(readings)
    with pytest.raises(ValueError):
        series_messages({"payload_kind": "computed:derived", "series": []})


def test_archived_payloads_convert_for_every_kind():
    position = payload_message("device:position", {"latitude_i": 414000000, "longitude_i": 21700000})
    assert position.latitude_i == 414000000
    user = payload_message("device:nodeinfo", {"long_name": "Roof", "short_name": "RF"})
    assert user.long_name == "Roof"
    with pytest.raises(ValueError):
        payload_message("computed:derived", {})
