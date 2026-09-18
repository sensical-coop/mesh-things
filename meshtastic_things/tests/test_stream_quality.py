"""Channel naming and window sizing - the shared logic behind the stream tier."""
import pytest

from common.channels import (
    DERIVED_KIND,
    NODEINFO_KIND,
    ORIGIN_COMPUTED,
    ORIGIN_DEVICE,
    ORIGIN_MEASURED,
    ORIGIN_OTHER,
    QUALITY_KIND,
    channel_name,
    channels_in,
    namespace_of,
    numeric_leaves,
    origin_of,
)
from common.detectors import (
    DEFAULT_FLAT_WINDOW,
    MAX_FLAT_WINDOW,
    MIN_FLAT_WINDOW,
    flat_window_for,
)


class TestChannelName:
    def test_strips_the_telemetry_prefix(self):
        # registry namespaces payload kinds; InfluxDB's measurement is bare.
        assert channel_name("telemetry:environment_metrics", "temperature") == (
            "environment_metrics.temperature"
        )

    def test_leaves_an_unprefixed_kind_alone(self):
        assert channel_name("position", "latitude_i") == "position.latitude_i"


class TestChannelsIn:
    def test_telemetry_submetric_becomes_the_measurement(self):
        # Must match writer/point_builders.py's naming, or a curated bound
        # would silently never match the channel it was curated for.
        payload = {"time": 123, "environment_metrics": {"temperature": 21.5, "relative_humidity": 48.0}}

        assert dict(channels_in("telemetry:environment_metrics", payload)) == {
            "environment_metrics.temperature": 21.5,
            "environment_metrics.relative_humidity": 48.0,
        }

    def test_several_submetrics_in_one_packet(self):
        payload = {"environment_metrics": {"temperature": 21.5}, "device_metrics": {"voltage": 4.1}}

        assert dict(channels_in("telemetry:environment_metrics", payload)) == {
            "environment_metrics.temperature": 21.5,
            "device_metrics.voltage": 4.1,
        }

    def test_flat_payload_falls_back_to_the_payload_kind(self):
        # position/nodeinfo have numeric leaves at the top level, and
        # point_builders uses the payload kind as their measurement.
        assert dict(channels_in("position", {"latitude_i": 411234567, "longitude_i": 21234567})) == {
            "position.latitude_i": 411234567,
            "position.longitude_i": 21234567,
        }

    def test_skips_non_numeric_and_bool_values(self):
        payload = {"environment_metrics": {"temperature": 21.5, "name": "sensor", "ok": True}}

        assert dict(channels_in("telemetry:environment_metrics", payload)) == {
            "environment_metrics.temperature": 21.5
        }

    def test_skips_the_time_key(self):
        assert dict(channels_in("telemetry:device_metrics", {"time": 1234567})) == {}

    def test_empty_and_missing_payload(self):
        assert dict(channels_in("telemetry:device_metrics", {})) == {}
        assert dict(channels_in("telemetry:device_metrics", None)) == {}

    def test_channels_in_agrees_with_channel_name(self):
        # The two entry points must not drift - registry builds the config key
        # with channel_name, the stream tier looks it up with channels_in.
        payload = {"environment_metrics": {"temperature": 21.5}}
        produced = next(iter(dict(channels_in("telemetry:environment_metrics", payload))))
        assert produced == channel_name("telemetry:environment_metrics", "temperature")


class TestNumericLeaves:
    def test_recurses_into_nested_dicts(self):
        assert dict(numeric_leaves({"a": {"b": {"c": 1.0}}, "d": 2})) == {"c": 1.0, "d": 2}

    def test_excludes_bools(self):
        # bool is an int subclass in Python; a flag isn't a measurement.
        assert dict(numeric_leaves({"ok": True, "value": 1})) == {"value": 1}


class TestFlatWindowFor:
    def test_no_interval_falls_back_to_the_fixed_default(self):
        assert flat_window_for(None) == DEFAULT_FLAT_WINDOW
        assert flat_window_for(0) == DEFAULT_FLAT_WINDOW

    def test_window_is_derived_from_the_reading_interval(self):
        # 3h at a 15min interval = 12 readings.
        assert flat_window_for(900, hours=3) == 12
        # The same 3h at 30s is far more readings - the whole point of
        # deriving the window instead of using a fixed count.
        assert flat_window_for(30, hours=3) == 240

    def test_window_is_clamped_at_both_ends(self):
        # A huge interval would otherwise give a window of 0 or 1.
        assert flat_window_for(86400, hours=3) == MIN_FLAT_WINDOW
        # A tiny interval would otherwise blow up per-key state.
        assert flat_window_for(1, hours=24) == MAX_FLAT_WINDOW

    @pytest.mark.parametrize("interval", [30, 60, 300, 900, 3600])
    def test_window_stays_within_bounds_for_realistic_intervals(self, interval):
        assert MIN_FLAT_WINDOW <= flat_window_for(interval) <= MAX_FLAT_WINDOW


class TestOriginOf:
    """`origin` tells a consumer whether a channel is a sensor reading or something the system
    computed - so it doesn't plot completeness_ratio next to temperature.
"""

    def test_telemetry_is_measured(self):
        assert origin_of("telemetry:environment_metrics") == ORIGIN_MEASURED

    def test_blueprint_output_is_computed(self):
        assert origin_of(DERIVED_KIND) == ORIGIN_COMPUTED

    def test_quality_is_computed(self):
        assert origin_of(QUALITY_KIND) == ORIGIN_COMPUTED

    def test_self_reported_is_device(self):
        assert origin_of(NODEINFO_KIND) == ORIGIN_DEVICE

    def test_unknown_namespace_falls_back(self):
        assert origin_of("something:else") == ORIGIN_OTHER
        assert origin_of("") == ORIGIN_OTHER
        assert origin_of(None) == ORIGIN_OTHER


class TestComputedChannelNames:
    """A payload_kind's measurement half has to name the InfluxDB series that actually exists,
    or the catalog's channel matches nothing.
"""

    def test_derived_channel_matches_the_influx_series(self):
        # Every blueprint output goes to measurement "derived", attributed by
        # the point's blueprint_id tag, so this must be "derived.dew_point".
        assert channel_name(DERIVED_KIND, "dew_point") == "derived.dew_point"

    def test_quality_channel_matches_the_influx_series(self):
        assert channel_name(QUALITY_KIND, "completeness_ratio") == "quality.completeness_ratio"

    def test_a_blueprint_scoped_payload_kind_would_not_match(self):
        # Why the measurement half is "derived" rather than the blueprint name:
        # "computed:weather-v1" yields a measurement write_derived never writes.
        assert channel_name("computed:weather-v1", "dew_point") != "derived.dew_point"


class TestNamespaceOf:
    def test_prefixed(self):
        assert namespace_of("telemetry:environment_metrics") == "telemetry"

    def test_flat(self):
        assert namespace_of("quality") == "quality"
