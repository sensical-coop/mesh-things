"""Tests for influx route params"""
from datetime import date, datetime, timezone
from unittest.mock import MagicMock

from django.test import SimpleTestCase
from influxdb_client.client.flux_table import FluxRecord

from common.alarm_counts import ALARM_COUNTS_BUCKET, ALARMS_BUCKET
from common.mesh_stats import MESH_STATS_BUCKET
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

    def test_readings_come_from_the_readings_bucket(self):
        self.assertIn('from(bucket: "telemetry")', self._flux())

    def test_alarms_come_from_their_own_bucket(self):
        self.assertIn(f'from(bucket: "{ALARMS_BUCKET}")', self._flux(measurement="alarms"))

    def test_latest_alarms_come_from_their_own_bucket(self):
        self.client.latest(MESH_ID, 123, "alarms")

        self.assertIn(f'from(bucket: "{ALARMS_BUCKET}")', self.client._query_api.query.call_args.args[0])

    def test_latest_of_everything_includes_the_alarms(self):
        self.client._query_api.query.return_value = []

        self.client.latest_all(MESH_ID, 123)

        buckets = [c.args[0].split('from(bucket: "')[1].split('"')[0] for c in self.client._query_api.query.call_args_list]
        self.assertEqual(buckets, ["telemetry", ALARMS_BUCKET])


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

    def _range_hours(self, hours):
        return [_FakeTable([_FakeRecord({}, "_value", hours)])]

    def test_queries_quality_then_alarms_filtered_by_mesh_and_node(self):
        self.client._query_api.query.side_effect = [self._quality_tables(), self._alarm_tables(), [], []]

        self.client.device_metrics(MESH_ID, 123, "-1h", "now()")

        quality_flux, alarms_flux, _, _ = (c.args[0] for c in self.client._query_api.query.call_args_list)
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
            [],
            [],
        ]

        result = self.client.device_metrics(MESH_ID, 123, "-1h", "now()")

        self.assertEqual(result["points_ingested"], 270.0)
        self.assertEqual({c["channel"] for c in result["channels"]}, {"device_metrics.battery_level", "environment_metrics.temperature"})

    def test_range_ratio_is_the_share_of_reported_hours_without_a_range_alarm(self):
        self.client._query_api.query.side_effect = [
            self._quality_tables(observed=200.0),
            self._alarm_tables(range=6, completeness=1),
            self._range_hours(6),
            self._range_hours(12),
        ]

        # 24 h asked for, but the device only reported in 12 of them.
        result = self.client.device_metrics(MESH_ID, 123, "-24h", "now()")

        self.assertEqual(result["alarms_by_detector"], {"range": 6, "completeness": 1})
        self.assertAlmostEqual(result["range_ratio"], 1 - 6 / 12)

    def test_range_ratio_is_none_when_the_device_did_not_report(self):
        self.client._query_api.query.side_effect = [[], [], [], []]

        result = self.client.device_metrics(MESH_ID, 123, "-1h", "now()")

        self.assertEqual(result["points_ingested"], 0)
        self.assertIsNone(result["range_ratio"])
        self.assertEqual(result["channels"], [])
        self.assertEqual(result["alarms_by_detector"], {})

    def test_a_recent_range_reads_each_alarm(self):
        self.client._query_api.query.side_effect = [[], [], [], []]

        self.client.device_metrics(MESH_ID, 123, "-30d", "now()")

        alarms_flux = self.client._query_api.query.call_args_list[1].args[0]
        self.assertIn(f'from(bucket: "{ALARMS_BUCKET}")', alarms_flux)
        self.assertIn("count()", alarms_flux)

    def test_a_range_reaching_past_the_retention_reads_the_daily_counts(self):
        self.client._query_api.query.side_effect = [[], [], [], []]

        self.client.device_metrics(MESH_ID, 123, "-31d", "now()")

        alarms_flux, range_flux, _ = (c.args[0] for c in self.client._query_api.query.call_args_list[1:])
        self.assertIn(f'from(bucket: "{ALARM_COUNTS_BUCKET}")', alarms_flux)
        self.assertIn('r._field == "alarms"', alarms_flux)
        self.assertIn('r._field == "hours_active"', range_flux)

    def test_an_absolute_range_is_placed_against_now(self):
        self.client._query_api.query.side_effect = [[], [], [], []]
        now = datetime(2026, 9, 29, tzinfo=timezone.utc)

        self.client.device_metrics(MESH_ID, 123, "2026-08-01", "2026-08-02", now=now)

        alarms_flux = self.client._query_api.query.call_args_list[1].args[0]
        self.assertIn(ALARM_COUNTS_BUCKET, alarms_flux)

    def test_invalid_mesh_id_is_rejected_before_querying(self):
        with self.assertRaises(ValueError):
            self.client.device_metrics("not-a-uuid", 123, "-1h", "now()")
        self.client._query_api.query.assert_not_called()


class DayRowsTests(SimpleTestCase):
    def setUp(self):
        self.client = InfluxQueryClient.__new__(InfluxQueryClient)
        self.client.bucket = "telemetry"
        self.client._query_api = MagicMock()

    @staticmethod
    def record(measurement, field, value, minute, node_id="7", **tags):
        values = {
            "result": "_result", "table": 0, "_measurement": measurement, "_field": field, "_value": value,
            "_time": datetime(2026, 9, 1, 13, minute, tzinfo=timezone.utc), "mesh_id": MESH_ID, "node_id": node_id,
            "gateway_id": "!aabbccdd", **tags,
        }
        return FluxRecord(table=0, values=values)

    def test_fields_of_one_time_and_node_share_a_row(self):
        self.client._query_api.query_stream.return_value = iter([
            self.record("environment_metrics", "temperature", 21.5, 5),
            self.record("environment_metrics", "relative_humidity", 40.0, 5),
            self.record("environment_metrics", "temperature", 22.0, 1, node_id="10"),
            self.record("nodeinfo", "user_id", "!0000000a", 0, node_id="10", long_name="Roof"),
        ])

        out = self.client.day_rows(MESH_ID, date(2026, 9, 1))

        env = out["environment_metrics"]
        self.assertEqual(env["fields"], ["relative_humidity", "temperature"])
        self.assertEqual(env["tags"], [])
        self.assertEqual(env["rows"], [
            {"time": "2026-09-01T13:01:00Z", "node_id": 10, "temperature": 22.0},
            {"time": "2026-09-01T13:05:00Z", "node_id": 7, "temperature": 21.5, "relative_humidity": 40.0},
        ])
        self.assertEqual(out["nodeinfo"]["tags"], ["long_name"])
        self.assertEqual(out["nodeinfo"]["rows"][0]["long_name"], "Roof")

    def test_the_query_covers_one_utc_day_without_quality(self):
        self.client._query_api.query_stream.return_value = iter([])

        self.client.day_rows(MESH_ID, date(2026, 9, 1), node_ids=[7, 10])

        flux = self.client._query_api.query_stream.call_args.args[0]
        self.assertIn("range(start: 2026-09-01T00:00:00Z, stop: 2026-09-02T00:00:00Z)", flux)
        self.assertIn('r._measurement != "quality"', flux)
        self.assertIn('(r.node_id == "7" or r.node_id == "10")', flux)


class MeshStatsTests(SimpleTestCase):
    """Flux shape and how the result tables are folded"""

    T0 = datetime(2026, 10, 1, tzinfo=timezone.utc)

    def setUp(self):
        self.client = InfluxQueryClient.__new__(InfluxQueryClient)
        self.client.bucket = "telemetry"
        self.client._query_api = MagicMock()

    def _table(self, *values):
        return _FakeTable([FluxRecord(table=0, values={"_time": self.T0, **v}) for v in values])

    def _run(self):
        self.client._query_api.query.side_effect = [
            [self._table({"portnum": "67", "_field": "packets", "_value": 3}, {"portnum": "67", "_field": "receptions", "_value": 6})],
            [self._table({"portnum": "67", "_value": 6})],
            [self._table({"node_id": "7", "_field": "packets", "_value": 3})],
            [self._table({"gateway_id": "100", "_field": "receptions", "_value": 6})],
            [self._table({"hops": "0", "_field": "packets", "_value": 3})],
            [self._table({"metric": "snr", "bucket": "5", "_field": "receptions", "_value": 6})],
            [self._table({"_field": "channel_utilization", "_value": 12.5})],
            [self._table({"_field": "channel_utilization", "_value": 40.0})],
            [self._table({"_field": "channel_utilization", "_value": 12.5})],
        ]
        result = self.client.mesh_stats(MESH_ID, "-24h", "2026-09-30T00:00:00Z", "15m")
        return result, [c.args[0] for c in self.client._query_api.query.call_args_list]

    def test_reads_traffic_per_minute_and_the_rest_from_whole_hours(self):
        _, queries = self._run()

        for flux in queries[:6]:
            self.assertIn(f'from(bucket: "{MESH_STATS_BUCKET}")', flux)
            self.assertIn(f'r.mesh_id == "{MESH_ID}"', flux)
        self.assertIn("range(start: -24h)", queries[0])
        self.assertIn("aggregateWindow(every: 15m, fn: sum, createEmpty: false)", queries[1])
        for flux in queries[2:6]:
            self.assertIn("range(start: 2026-09-30T00:00:00Z)", flux)
        self.assertIn('group(columns: ["metric", "bucket", "_field"])', queries[5])
        self.assertIn('from(bucket: "telemetry")', queries[6])

    def test_folds_tables_by_their_tags(self):
        result, _ = self._run()

        self.assertEqual(
            result["traffic"],
            {"67": {"packets": 3, "receptions": 6, "points": [{"time": self.T0.isoformat(), "value": 6}]}},
        )
        self.assertEqual(result["nodes"], {"7": {"packets": 3}})
        self.assertEqual(result["gateways"], {"100": {"receptions": 6}})
        self.assertEqual(result["hops"], {"0": {"packets": 3}})
        self.assertEqual(result["signal"], {("snr", "5"): {"receptions": 6}})
        self.assertEqual(result["airtime"]["channel_utilization"]["peak"], 40.0)

    def test_rejects_an_invalid_window_before_querying(self):
        with self.assertRaises(ValueError):
            self.client.mesh_stats(MESH_ID, "-24h", "2026-09-30T00:00:00Z", "15m) |> drop(")
        self.client._query_api.query.assert_not_called()
