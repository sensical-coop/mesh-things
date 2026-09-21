"""Tests for influx route params"""
from unittest.mock import MagicMock

from django.test import SimpleTestCase

from readings.influx_client import InfluxQueryClient

MESH_ID = "11111111-2222-3333-4444-555555555555"


class TimeseriesFluxTests(SimpleTestCase):
    def setUp(self):
        self.client = InfluxQueryClient.__new__(InfluxQueryClient)  # no real connection
        self.client.bucket = "telemetry"
        self.client._query_api = MagicMock()
        self.client._query_api.query.return_value = []

    def _flux(self, **overrides):
        kwargs = {
            "mesh_id": MESH_ID,
            "node_id": 123,
            "measurement": "environment_metrics",
            "field": None,
            "start": "-24h",
            "stop": "now()",
            "window": None,
            "agg": "mean",
        }
        kwargs.update(overrides)
        self.client.timeseries(**kwargs)
        return self.client._query_api.query.call_args.args[0]

    def test_windowed_query_aggregates_numeric_fields_only(self):
        # Guards Flux's 'unsupported input type for mean aggregate: string'.
        flux = self._flux(window="6h")

        self.assertIn('import "types"', flux)
        self.assertIn('types.isType(v: r._value, type: "float")', flux)
        self.assertIn('types.isType(v: r._value, type: "int")', flux)
        self.assertIn("aggregateWindow(every: 6h, fn: mean, createEmpty: false)", flux)
        self.assertLess(flux.index("types.isType"), flux.index("aggregateWindow"))

    def test_unwindowed_query_keeps_string_fields(self):
        # No aggregation means no reason to drop stuff
        flux = self._flux()

        self.assertNotIn("types.isType", flux)
        self.assertNotIn('import "types"', flux)
        self.assertNotIn("aggregateWindow", flux)

    def test_agg_function_is_interpolated_from_the_validated_set(self):
        self.assertIn("fn: max", self._flux(window="1h", agg="max"))

    def test_invalid_agg_is_rejected_before_reaching_flux(self):
        with self.assertRaises(ValueError):
            self._flux(window="1h", agg="drop")
        self.client._query_api.query.assert_not_called()

    def test_field_filter_is_applied_when_given(self):
        self.assertIn('r._field == "temperature"', self._flux(field="temperature"))

    def test_absolute_bounds_reach_the_range_call_as_utc_timestamps(self):
        flux = self._flux(start="2026-09-01", stop="2026-09-02T13:45:00Z")

        self.assertIn("range(start: 2026-09-01T00:00:00Z, stop: 2026-09-02T13:45:00Z)", flux)

    def test_relative_and_absolute_bounds_can_be_mixed(self):
        self.assertIn("range(start: 2026-09-01T00:00:00Z, stop: now())", self._flux(start="2026-09-01"))


class _FakeRecord:
    def __init__(self, values, field, value):
        self.values = values
        self._field = field
        self._value = value

    def get_field(self):
        return self._field

    def get_value(self):
        return self._value


class _FakeTable:
    def __init__(self, records):
        self.records = records


class DeviceMetricsTests(SimpleTestCase):
    """Flux filters and the derived ratios"""

    def setUp(self):
        self.client = InfluxQueryClient.__new__(InfluxQueryClient)
        self.client.bucket = "telemetry"
        self.client._query_api = MagicMock()

    def _quality_tables(self, channel="device_metrics.battery_level", **fields):
        values = {"completeness_ratio": 0.95, "observed": 190.0, "expected": 200.0, "largest_gap_seconds": 300.0}
        values.update(fields)
        return [_FakeTable([_FakeRecord({"channel": channel}, field, value)]) for field, value in values.items()]

    @staticmethod
    def _channel_table(channel, field, value):
        return _FakeTable([_FakeRecord({"channel": channel}, field, value)])

    def _alarm_tables(self, **counts):
        return [_FakeTable([_FakeRecord({"detector": detector}, "_value", count)]) for detector, count in counts.items()]

    def test_queries_quality_then_alarms_filtered_by_mesh_and_node(self):
        self.client._query_api.query.side_effect = [self._quality_tables(), self._alarm_tables()]

        self.client.device_metrics(MESH_ID, 123, "-1h", "now()")

        quality_flux, alarms_flux = (c.args[0] for c in self.client._query_api.query.call_args_list)
        self.assertIn('r._measurement == "quality"', quality_flux)
        self.assertIn(f'r.mesh_id == "{MESH_ID}"', quality_flux)
        self.assertIn('r.node_id == "123"', quality_flux)
        self.assertIn('r._measurement == "alarms"', alarms_flux)
        self.assertIn(f'r.mesh_id == "{MESH_ID}"', alarms_flux)

    def test_points_ingested_sums_observed_across_channels(self):
        self.client._query_api.query.side_effect = [
            [
                self._channel_table("device_metrics.battery_level", "observed", 190.0),
                self._channel_table("environment_metrics.temperature", "observed", 80.0),
            ],
            self._alarm_tables(),
        ]

        result = self.client.device_metrics(MESH_ID, 123, "-1h", "now()")

        self.assertEqual(result["points_ingested"], 270.0)
        self.assertEqual({c["channel"] for c in result["channels"]}, {"device_metrics.battery_level", "environment_metrics.temperature"})

    def test_range_ratio_derived_from_range_alarms(self):
        self.client._query_api.query.side_effect = [
            self._quality_tables(observed=200.0),
            self._alarm_tables(range=2, completeness=1),
        ]

        result = self.client.device_metrics(MESH_ID, 123, "-1h", "now()")

        self.assertEqual(result["alarms_by_detector"], {"range": 2, "completeness": 1})
        self.assertAlmostEqual(result["range_ratio"], 1 - 2 / 200.0)

    def test_range_ratio_is_none_when_nothing_was_ingested(self):
        self.client._query_api.query.side_effect = [[], []]

        result = self.client.device_metrics(MESH_ID, 123, "-1h", "now()")

        self.assertEqual(result["points_ingested"], 0)
        self.assertIsNone(result["range_ratio"])
        self.assertEqual(result["channels"], [])
        self.assertEqual(result["alarms_by_detector"], {})

    def test_invalid_mesh_id_is_rejected_before_querying(self):
        with self.assertRaises(ValueError):
            self.client.device_metrics("not-a-uuid", 123, "-1h", "now()")
        self.client._query_api.query.assert_not_called()
